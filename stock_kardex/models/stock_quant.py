import logging
from collections import defaultdict

from odoo import api, models

from .helper import _harmonize_empty_values, _transform_location, _update_locations

_logger = logging.getLogger(__name__)

# LocationName values that _transform_location produces for the Kardex and the palettes
SHUTTLE = "Shuttle"
PALETTE = "Palette"


class StockQuant(models.Model):
    _name = "stock.quant"
    _inherit = ["stock.quant", "base.kardex.mixin"]
    _description = "Stock Quant"

    def _get_kardex_location(self):
        """The one location flagged Kardex (stock_location.kardex)."""
        return self.env["stock.location"].search([("kardex", "=", True)], limit=1)

    def _get_palette_location(self):
        """The one location flagged Palette (stock_location.palette)."""
        return self.env["stock.location"].search([("palette", "=", True)], limit=1)

    def _get_data_from_bestandsabgleich(self, default_code=None):
        """Latest stock per product, serial and lot from PPG_Bestandsabgleich.

        The table only knows the Kardex itself, so every row is located in the shuttle.
        """
        conditions, params = "", []
        if default_code:
            conditions = f"WHERE Suchbegriff = {self._sql_placeholder()}"
            params = [(default_code,)]
        ppg_sql = f"""
            WITH RankedRows AS (
                SELECT
                    Suchbegriff,
                    Seriennummer,
                    Charge,
                    Row_Create_Time,
                    Bestand,
                    ROW_NUMBER() OVER (
                        PARTITION BY Suchbegriff, COALESCE(Seriennummer, 'NO_SN'), COALESCE(Charge, 'NO_LOT')
                        ORDER BY Row_Create_Time DESC
                    ) AS rn
                FROM PPG_Bestandsabgleich
                {conditions}
            )
            SELECT Suchbegriff, Seriennummer, Charge, Row_Create_Time, Bestand
            FROM RankedRows
            WHERE rn = 1
            ORDER BY Suchbegriff, Seriennummer, Charge;
        """
        rows = self._execute_query_on_mssql("select", ppg_sql, *params)
        for row in rows:
            row["LocationName"] = SHUTTLE
        return rows

    def _get_data_direct_call(self, default_code=None, products=None):
        """Materials and stock rows from the ProdDB, renamed to the PPG_Bestandsabgleich columns."""
        replace_dict = {
            "Produktnr": "Suchbegriff",
            "Lot": "Charge",
            "Serialnumber": "Seriennummer",
            "QuantityCurrent": "Bestand",
        }
        replace_dict_material = {
            "MaterialName": "Suchbegriff",
        }

        data_material, data = self._read_external_object_from_proddb(default_code, products)
        updated_data = [{replace_dict.get(k, k): v for k, v in item.items()} for item in data]
        updated_data_material = [
            {replace_dict_material.get(k, k): v for k, v in item.items()} for item in data_material
        ]

        return updated_data_material, updated_data

    def _get_or_create_location(self, location_name):
        """Odoo location of a Kardex LocationName; unknown names are created below the stock location."""
        if location_name == SHUTTLE:
            return self._get_kardex_location()
        if location_name == PALETTE and self._get_palette_location():
            return self._get_palette_location()
        location = self.env["stock.location"].search([("name", "=", location_name)], limit=1)
        if not location:
            kardex_location = self._get_kardex_location()
            parent = kardex_location.warehouse_id.lot_stock_id or self.env.ref("stock.stock_location_stock")
            location = self.env["stock.location"].create({"name": location_name, "location_id": parent.id})
        return location

    @api.model
    def sync_stocks(self, default_code=None, all_products=False, all_locations=False, source_sale_order=False):
        """Set the Odoo quants to the stock reported by Kardex.

        :param default_code: sync only this product, otherwise all products with a default code
        :param all_products: sync even if there is no quant in the Kardex location yet
        :param all_locations: sync every location reported by Kardex, not only the Kardex itself
        :param source_sale_order: unused, kept for the callers
        """
        param = self.env["ir.config_parameter"].sudo()
        remove_quants = param.get_param("kardex.remove_quants") == "True"
        aggregate_palettes = param.get_param("kardex.aggregate_palettes") == "True"
        last_location_partial = param.get_param("kardex.last_location_partial") == "True"

        kardex_location = self._get_kardex_location()
        if not kardex_location:
            return False

        product_mapping = self._get_product_mapping(default_code)
        quant_mapping = self._get_quant_mapping(kardex_location, all_locations)
        if not all_products and not default_code and not any(product for product, _lot, _loc in quant_mapping):
            return False

        kardex_data = self._get_kardex_stock_data(default_code, product_mapping, kardex_location)
        if kardex_data is None:
            _logger.warning("Stock sync skipped: neither the Kardex DB nor the ProdDB is connected.")
            return False

        kardex_data = _update_locations(kardex_data, lambda loc: _transform_location(loc, aggregate_palettes))
        kardex_data = _harmonize_empty_values(kardex_data)
        self._set_last_location_to_kardex(
            kardex_data, product_mapping, kardex_location, aggregate_palettes, last_location_partial
        )
        kardex_data = self._aggregate_kardex_data(kardex_data)
        _logger.info("kardex_data after grouping: %s", kardex_data)

        synced_quant_ids = self._apply_kardex_data(
            kardex_data, product_mapping, quant_mapping, kardex_location, all_locations
        )
        self._reset_quants_missing_in_kardex(synced_quant_ids, kardex_location, all_locations, remove_quants)
        return True

    def _get_product_mapping(self, default_code=None):
        """{default_code: product_id} of the products to sync."""
        query = """
            SELECT pt.default_code, pp.id
            FROM product_product pp
            JOIN product_template pt ON pp.product_tmpl_id = pt.id
        """
        if default_code:
            self.env.cr.execute(query + " WHERE pt.default_code = %s", (default_code,))
        else:
            self.env.cr.execute(query + " WHERE pt.default_code IS NOT NULL")
        return dict(self.env.cr.fetchall())

    def _get_quant_mapping(self, kardex_location, all_locations):
        """{(product_id, lot_id, location_id): quant_id} of the quants that may be synced."""
        if all_locations:
            self.env.cr.execute("SELECT id, product_id, lot_id, location_id FROM stock_quant")
        else:
            self.env.cr.execute(
                "SELECT id, product_id, lot_id, location_id FROM stock_quant WHERE location_id = %s",
                (kardex_location.id,),
            )
        return {(product, lot, location): quant for quant, product, lot, location in self.env.cr.fetchall()}

    def _get_kardex_stock_data(self, default_code, product_mapping, kardex_location):
        """Stock rows from the source chosen in the settings (kardex.inv_method).

        Falls back to the other source if the chosen one is not connected and
        returns None if none is connected.
        """
        mixin = self.env["base.kardex.mixin"]
        inv_method = self.env["ir.config_parameter"].sudo().get_param("kardex.inv_method", "ppg")
        proddb_connected = mixin._is_proddb_connected()
        kardex_db_connected = mixin._is_kardex_db_connected()

        if proddb_connected and (inv_method == "direct" or not kardex_db_connected):
            data_material, kardex_data = self._get_data_direct_call(default_code=default_code, products=product_mapping)
            self._reset_materials_without_stock(data_material, kardex_data, product_mapping, kardex_location)
            return kardex_data
        if kardex_db_connected:
            return self._get_data_from_bestandsabgleich(default_code)
        return None

    def _reset_materials_without_stock(self, data_material, kardex_data, product_mapping, kardex_location):
        """Set the Kardex quants to zero for materials the ProdDB knows but has no stock of."""
        codes_with_stock = {row["Suchbegriff"] for row in kardex_data}
        product_ids = tuple(
            product_mapping[row["Suchbegriff"]]
            for row in data_material
            if row["Suchbegriff"] not in codes_with_stock and row["Suchbegriff"] in product_mapping
        )
        if product_ids:
            self.env.cr.execute(
                "UPDATE stock_quant SET quantity = 0 WHERE product_id IN %s AND location_id = %s",
                (product_ids, kardex_location.id),
            )

    def _set_last_location_to_kardex(
        self, kardex_data, product_mapping, kardex_location, aggregate_palettes, partial=False
    ):
        """Remember the Kardex as last location of products that are stored nowhere else.

        :param partial: also of products that are only partly stored in the Kardex
        """
        kardex_names = {SHUTTLE, PALETTE} if aggregate_palettes else {SHUTTLE}
        locations_by_code = defaultdict(set)
        for row in kardex_data:
            locations_by_code[row["Suchbegriff"]].add(row["LocationName"])

        product_ids = [
            product_mapping[code]
            for code, locations in locations_by_code.items()
            if code in product_mapping and (locations & kardex_names if partial else locations <= kardex_names)
        ]
        self.env["product.product"].browse(product_ids).write({"last_location_id": kardex_location.id})

    def _aggregate_kardex_data(self, kardex_data):
        """Sum the stock per product, lot and location; serial numbers without lot stay single rows."""
        grouped = {}
        serial_rows = []
        for row in kardex_data:
            if row["Charge"] is None and row["Seriennummer"] is not None:
                serial_rows.append(row)
                continue
            key = (row["Suchbegriff"], row["Charge"], row["LocationName"])
            group = grouped.setdefault(
                key,
                {
                    "Suchbegriff": row["Suchbegriff"],
                    "Charge": row["Charge"],
                    "Seriennummer": None,
                    "LocationName": row["LocationName"],
                    "Bestand": 0.0,
                },
            )
            group["Bestand"] += row["Bestand"] or 0.0
        return list(grouped.values()) + serial_rows

    def _apply_kardex_data(self, kardex_data, product_mapping, quant_mapping, kardex_location, all_locations):
        """Write the Kardex stock into the quants and log the changes in a sync report.

        Returns {product_id: [quant_id]} of the quants that were set.
        """
        report = self.env["kardex.sync.report"].create({"name": "Sync Bestandsabgleich"})
        company_id = kardex_location.company_id.id or self.env.company.id
        lot_mapping = self._get_lot_mapping()
        synced_quant_ids = defaultdict(list)

        for row in kardex_data:
            product_id = product_mapping.get(row["Suchbegriff"])
            if not product_id:
                continue
            if not all_locations and row["LocationName"] not in (SHUTTLE, kardex_location.name):
                continue

            location = self._get_or_create_location(row["LocationName"])
            lot_name = row["Seriennummer"] or row["Charge"]
            quantity = row["Bestand"]
            changes = []

            lot_id = None
            if lot_name:
                lot_id = lot_mapping.get((lot_name, product_id))
                if not lot_id:
                    lot_id = self._create_lot(lot_name, product_id, location.id)
                    lot_mapping[(lot_name, product_id)] = lot_id
                    changes.append(f"new lot: {lot_name}")

            quant_id = quant_mapping.get((product_id, lot_id, location.id))
            if quant_id:
                self.env.cr.execute("UPDATE stock_quant SET quantity = %s WHERE id = %s", (quantity, quant_id))
                changes.append(f"lot: {lot_name or '-'}, loc: {location.id}, qty: → {quantity}")
            else:
                quant_id = self._create_quant(product_id, lot_id, location.id, quantity, company_id)
                quant_mapping[(product_id, lot_id, location.id)] = quant_id
                changes.append(f"lot: {lot_name or '-'}, loc: {location.id}, qty: → {quantity} (new)")
            synced_quant_ids[product_id].append(quant_id)

            self.env["kardex.sync.report.line"].create(
                {"report_id": report.id, "product_id": product_id, "changes": "\n".join(changes)}
            )

        self.env["stock.quant"].invalidate_model(["quantity"])
        return synced_quant_ids

    def _get_lot_mapping(self):
        """{(lot_name, product_id): lot_id} of all lots."""
        self.env.cr.execute("SELECT name, product_id, id FROM stock_lot")
        return {(name, product): lot for name, product, lot in self.env.cr.fetchall()}

    def _create_lot(self, lot_name, product_id, location_id):
        self.env.cr.execute(
            """
            INSERT INTO stock_lot (name, product_id, location_id, create_date)
            VALUES (%s, %s, %s, NOW())
            RETURNING id
            """,
            (lot_name, product_id, location_id),
        )
        return self.env.cr.fetchone()[0]

    def _create_quant(self, product_id, lot_id, location_id, quantity, company_id):
        self.env.cr.execute(
            """
            INSERT INTO stock_quant (
                product_id, lot_id, quantity, reserved_quantity, location_id, company_id, in_date, create_date
            )
            VALUES (%s, %s, %s, 0, %s, %s, NOW(), NOW())
            RETURNING id
            """,
            (product_id, lot_id, quantity, location_id, company_id),
        )
        return self.env.cr.fetchone()[0]

    def _reset_quants_missing_in_kardex(self, synced_quant_ids, kardex_location, all_locations, remove_quants):
        """Set the quants of the synced products to zero that Kardex did not report.

        Only the synced locations are touched: the Kardex, or all internal locations
        with all_locations. With the setting kardex.remove_quants the Kardex quants
        are deleted instead.
        """
        location_domain = (
            [("location_id.usage", "=", "internal")] if all_locations else [("location_id", "=", kardex_location.id)]
        )
        for product_id, quant_ids in synced_quant_ids.items():
            missing_quants = self.env["stock.quant"].search(
                [("product_id", "=", product_id), ("id", "not in", quant_ids)] + location_domain
            )
            _logger.info("Quants missing in Kardex data: %s", missing_quants)
            missing_quants.write({"quantity": 0})
            if remove_quants:
                missing_quants.filtered(lambda quant: quant.location_id == kardex_location).unlink()
