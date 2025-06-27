import logging
from collections import defaultdict

from odoo import api, models

from .config import (
    AGGREGATE_PALETTEN,
    COMPANY_ID,
    KARDEX_WAREHOUSE,
    NON_KARDEX_WAREHOUSE,
    PALETTEN_WAREHOUSE,
    STOCK_WAREHOUSE,
    USE_BESTANDSABGLEICH_FOR_SYNC_STOCKS,
)
from .helper import _harmonize_empty_values, _transform_location, _update_locations

_logger = logging.getLogger(__name__)


class StockQuant(models.Model):
    _name = "stock.quant"
    _inherit = ["stock.quant", "base.kardex.mixin"]
    _description = "Stock Quant"
    # _inherit = "stock.quant"

    def _get_location_id(self, location_name):
        location_id = self.env["stock.location"].search([("name", "=", location_name)]).mapped("id")
        return location_id

    def _get_data_from_bestandsabgleich(self, default_code, product_mapping):
        if default_code:
            conditions = f"WHERE Suchbegriff IN ('{default_code}')"
        else:
            # conditions = f"WHERE Suchbegriff IN ('ZUS.P020.0000.A')" # for testing
            # conditions = f"WHERE Suchbegriff IN ('MOT.101.000.003', 'FLB.101.000.002', 'DSU.101.000.001', 'GER.101.000.000')" # for testing
            conditions = f"WHERE Suchbegriff IN {tuple(product_mapping.keys())}"
        # conditions = f"WHERE ID > {START_STOCK_SYNC}"
        # get data from PPG_Bestandsabgleich
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

        ppg_data = self._execute_query_on_mssql("select", ppg_sql)

        return ppg_data

    def _get_data_direct_call(self, default_code=None, products=None):
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
        if location_name == "Shuttle":
            location = self.env["stock.location"].search([("name", "=", KARDEX_WAREHOUSE)], limit=1)
            return location.id, KARDEX_WAREHOUSE
        location = self.env["stock.location"].search([("name", "=", location_name)], limit=1)
        if not location:
            location_stock = self.env["stock.location"].search([("name", "=", STOCK_WAREHOUSE)], limit=1)
            location = self.env["stock.location"].create({"name": location_name, "location_id": location_stock.id})
        return location.id, location_name

    @api.model
    def sync_stocks(self, default_code=None, all_products=False, all_locations=False, source_sale_order=False):
        param = self.env["ir.config_parameter"].sudo()

        remove_quants = param.get_param("kardex.remove_quants") == "True"

        # get stock quants of Kardex Warehouse
        kardex_location_ids = self._get_location_id(KARDEX_WAREHOUSE)
        # _logger.info("location_ids: %s" % (location_ids,))
        if not kardex_location_ids:
            return False

        kardex_location_id = kardex_location_ids[0]

        non_kardex_location_ids = self._get_location_id(NON_KARDEX_WAREHOUSE)
        non_kardex_location_id = non_kardex_location_ids[0]

        kardex_location_name = self.env["stock.location"].browse(kardex_location_id).name
        # _logger.info("kardex_location_id: %s" % (kardex_location_id,))

        location_paletten_ids = self._get_location_id(PALETTEN_WAREHOUSE)
        # _logger.info("location_paletten_ids: %s" % (location_paletten_ids,))
        if not location_paletten_ids:
            return False

        location_paletten_id = location_paletten_ids[0]
        location_paletten_name = self.env["stock.location"].browse(location_paletten_id).name
        # _logger.info("location_paletten_id: %s" % (location_paletten_id,))

        # company id from settings
        company_id = COMPANY_ID

        # create dict with product ids and non empty default codes
        where = []
        params = []
        # default_codes = ['FLB.1037.28SW.RUND.A']
        default_codes = []
        query = """
            SELECT pt.default_code, pp.id
            FROM product_product pp
            JOIN product_template pt ON pp.product_tmpl_id = pt.id
        """
        if default_codes:
            where.append("pt.default_code IN %s")
            params.append(tuple(default_codes))
        else:
            where.append("pt.default_code IS NOT NULL")
        # for testing
        # import pdb; pdb.set_trace()
        if where:
            query += " WHERE " + " AND ".join(where)

        self.env.cr.execute(query, params)

        # self.env.cr.execute("""
        #     SELECT pt.default_code, pp.id
        #     FROM product_product pp
        #     JOIN product_template pt ON pp.product_tmpl_id = pt.id
        #     WHERE pt.default_code IS NOT NULL
        # """)
        # for testing

        # self.env.cr.execute("""
        #     SELECT pt.default_code, pp.id
        #     FROM product_product pp
        #     JOIN product_template pt ON pp.product_tmpl_id = pt.id
        #     WHERE pt.default_code IN ('BAG.1142.010C.V001', 'BAG.1149.010D.V001', 'BAG.1150.010A.V001', 'BAG.1152.010A.V001', 'BAG.1155.010A.V001', 'BAG.109A.0004.V001')
        # """)
        # self.env.cr.execute("""
        #     SELECT pt.default_code, pp.id
        #     FROM product_product pp
        #     JOIN product_template pt ON pp.product_tmpl_id = pt.id
        #     WHERE pt.default_code IN ('BAG.109A.0004.V001')
        # """)
        product_mapping = dict(self.env.cr.fetchall())
        _logger.warning("#### product_mapping: %s" % (product_mapping,))

        location_ids = (kardex_location_id, location_paletten_id, non_kardex_location_id)
        placeholders = ",".join(["%s"] * len(location_ids))

        if all_locations:
            odoo_sql = "SELECT id, product_id, lot_id, location_id FROM stock_quant"
            self.env.cr.execute(odoo_sql)

        else:
            odoo_sql = "SELECT id, product_id, lot_id, location_id FROM stock_quant WHERE location_id = %s"
            self.env.cr.execute(odoo_sql, (kardex_location_id,))

        # odoo_sql = "SELECT id, product_id, lot_id FROM stock_quant WHERE location_id IN (%s)"
        # self.env.cr.execute(odoo_sql, (location_id, location_paletten_id))

        # odoo_sql = f"SELECT id, product_id, lot_id FROM stock_quant WHERE location_id IN ({placeholders})"
        # self.env.cr.execute(odoo_sql, location_ids)
        stock_quants = self.env.cr.fetchall()

        stock_quant_mapping = {(p, l, loc): q for q, p, l, loc in stock_quants}

        # 2. Get existing lot_id mapping {lot_name → lot_id} for lots with location
        lots_sql = "SELECT name, product_id, id FROM stock_lot WHERE location_id IS NOT NULL"
        self.env.cr.execute(lots_sql)
        # lots = dict(self.env.cr.fetchall())  # {lot_name: lot_id}
        lots = self.env.cr.fetchall()

        lot_mapping = {(n, p): i for n, p, i in lots}

        products = tuple(set(q[1] for q in stock_quants if q[1]))
        # _logger.warning("#### products: %s" % (products,))

        if not all_products and not products and not default_code:
            return False  # No products to update

        if USE_BESTANDSABGLEICH_FOR_SYNC_STOCKS:
            kardex_data = self._get_data_from_bestandsabgleich(default_code, product_mapping)
        else:
            data_material, kardex_data = self._get_data_direct_call(default_code=default_code, products=product_mapping)

            kardex_data_values = {d["Suchbegriff"] for d in kardex_data}
            data_material_values = {d["Suchbegriff"] for d in data_material}

            # Find values in material data not in kardex _data -> material with no quantity
            not_in_kardex_data = data_material_values - kardex_data_values

            for product_key in not_in_kardex_data:
                quant_id = stock_quant_mapping.get((product_mapping.get(product_key), None, None))
                if quant_id:
                    self.env.cr.execute(
                        """
                        UPDATE stock_quant
                        SET quantity = 0
                        WHERE product_id = %s and location_id = %s
                    """,
                        (product_mapping[product_key], kardex_location_id),
                    )

        # _logger.info("### kardex_data: %s" % (kardex_data,))

        # update locations
        kardex_data = _update_locations(kardex_data, _transform_location)

        # harmonize empty values
        kardex_data = _harmonize_empty_values(kardex_data)

        # _logger.info("### kardex_data: %s" % (kardex_data,))

        # aggregate and grouping data
        grouped = {}
        grouped2 = {}  # will contain all Locations for product
        unaggregated = []

        palette_counter = 0

        for item in kardex_data:
            charge = item["Charge"]
            serial = item["Seriennummer"]
            suchbegriff = item["Suchbegriff"]
            location = item.get("LocationName")
            if location == "Palette":
                palette_counter += 1
            bestand = item.get("Bestand")

            if charge is None and serial is not None:
                unaggregated.append(item)  # Don't group, preserve as-is
                continue

            # Group by charge and Suchbegriff, to avoid merging unrelated products

            if charge:
                key = ("charge", charge, location, suchbegriff)
                if key not in grouped:
                    grouped[key] = {
                        "Charge": charge,
                        "Seriennummer": None,
                        "Suchbegriff": suchbegriff,
                        "LocationName": location,
                        "Bestand": 0.0,
                    }
                grouped[key]["Bestand"] += bestand

            else:
                key = ("no_charge", location, suchbegriff)
                if key not in grouped:
                    grouped[key] = {
                        "Charge": None,
                        "Seriennummer": None,
                        "Suchbegriff": suchbegriff,
                        "LocationName": location,
                        "Bestand": 0.0,
                    }
                grouped[key]["Bestand"] += bestand

            # if key not in grouped:
            #     grouped[key] = {
            #         'Charge': charge,
            #         'Suchbegriff': suchbegriff,
            #         'Seriennummer': serial,
            #         'Bestand': 0,
            #         'LocationName': location,
            #         'LocationNames': [],
            #     }

            # grouped[key]['Bestand'] += item['Bestand']
            # grouped[key]['LocationNames'].append(item['LocationName'])

            # group only by Suchbegriff
        for item in kardex_data:
            key2 = suchbegriff
            if key2 not in grouped2:
                grouped2[key2] = []

            grouped2[key2].append(item["LocationName"])

            # _logger.info("grouped: %s" % (grouped,))
            # _logger.info("grouped2: %s" % (grouped2,))
            # _logger.info("unaggregated: %s" % (unaggregated,))

            for key in grouped2.keys():
                if all(x == "Shuttle" or (x == "Palette" and AGGREGATE_PALETTEN) for x in grouped2[key]):
                    product = self.env["product.product"].search([("default_code", "=", suchbegriff)], limit=1)
                    product.write({"last_location_id": kardex_location_id})
                    _logger.info(
                        "product mit default_code %s wird auf last location  %s gesetzt"
                        % (
                            suchbegriff,
                            kardex_location_id,
                        )
                    )

        # Convert to list if needed
        kardex_data = list(grouped.values()) + unaggregated
        _logger.info("kardex_data after grouping: %s" % (kardex_data,))

        if palette_counter == 0 and source_sale_order and default_code:
            pass

        # stock_dict = {
        #     product_mapping[Suchbegriff]: Bestand
        #     for Suchbegriff, Bestand in self.env.cr.fetchall()
        #     if Suchbegriff in product_mapping
        # }

        # create report for sync actions
        report = self.env["kardex.sync.report"].create({"name": "Sync Bestandsabgleich"})

        existing_quant_map = defaultdict(list)

        for row in kardex_data:
            changes = []
            default_code = row["Suchbegriff"]

            # if product not listed in kardex then continue

            product_exists_in_kardex = any(default_code in d.values() for d in data_material)
            if not product_exists_in_kardex:
                continue

            # if row["Seriennummer"] not in ("", None):
            #     lot_name = row["Seriennummer"]
            # elif row["Charge"] not in ("", None):
            #     lot_name = row["Charge"]
            # else:
            #     lot_name = None
            lot_name = row.get("Seriennummer") or row.get("Charge") or None
            # _logger.info(f"### lot_name: {lot_name}")
            # _logger.info(f"### lot_name not in lot_mapping: {lot_name not in lot_mapping}")
            quantity = row["Bestand"]
            location = row["LocationName"]

            product_id = product_mapping.get(default_code)
            # _logger.info("### default_code: %s" % (default_code,))
            product = self.env["product.product"].search([("default_code", "=", default_code)], limit=1)
            # product_id = product.id

            _logger.info("### product_id: %s" % (product_id,))

            # quants of product with location = kardex
            existing_kardex_quants_ids_for_product = (
                self.env["stock.quant"]
                .search([("product_id", "=", product_id), ("location_id", "=", kardex_location_id)])
                .ids
            )
            _logger.info("### existing_kardex_quants_ids_for_product: %s" % (existing_kardex_quants_ids_for_product,))

            # loc_id =

            lot_id = lot_mapping.get((lot_name, product_id)) if lot_name and product_id else None
            # existing_kardex_quants_for_product = self.env["stock.quant"].search(
            #     [("product_id", "=", product_id), ("location_id", "=", location_id)]
            # )
            # _logger.info(f"### existing_kardex_quants_for_product: {existing_kardex_quants_for_product}")

            # get or create location
            location_id, location_name = self._get_or_create_location(location)
            if not all_locations and location_name != kardex_location_name:
                continue
            _logger.info(
                "### lot_name: %s, lot_id: %s, (product_id, lot_id, location_id) in stock_quant_mapping: %s, lot_name not in lot_mapping: %s"
                % (
                    lot_name,
                    lot_id,
                    (product_id, lot_id, location_id) in stock_quant_mapping,
                    lot_name not in lot_mapping,
                )
            )

            if lot_id and (product_id, lot_id, location_id) in stock_quant_mapping:
                _logger.info("### Case 1")
                # Case 1: Update existing stock_quant record with known lot for certain location
                quant_id = stock_quant_mapping[(product_id, lot_id, location_id)]

                self.env.cr.execute(
                    """
                    UPDATE stock_quant
                    SET quantity = %s
                    WHERE id = %s AND location_id = %s
                """,
                    (quantity, quant_id, location_id),
                )
                changes.append(f"lot: {lot_name}, loc: {location_id}, qty:  → {quantity}")
                existing_quant_map[product_id].append(quant_id)

                if quant_id and location_id == kardex_location_id:
                    existing_kardex_quants_ids_for_product.pop(quant_id)

            if lot_name and product_id and ((lot_name, product_id) not in lot_mapping):
                # Case 2: Create a new lot if necessary
                _logger.info("### Case 2")

                self.env.cr.execute(
                    """
                    INSERT INTO stock_lot (
                        name,
                        product_id,
                        location_id,
                        create_date
                    )
                    VALUES (
                        %s,
                        %s,
                        %s,
                        NOW()
                    )
                    RETURNING id
                """,
                    (lot_name, product_id, location_id),
                )
                lot_id = self.env.cr.fetchone()[0]
                lot_mapping[(lot_name, product_id)] = lot_id  # Update lot mapping

                _logger.warning(
                    "### bestand anlegen fuer lot_id: %s, location: %s , location id: %s"
                    % (lot_id, location, location_id)
                )

                # Insert new stock_quant record for product with this lot
                self.env.cr.execute(
                    """
                    INSERT INTO stock_quant (
                        product_id,
                        lot_id,
                        quantity,
                        reserved_quantity,
                        location_id,
                        company_id,
                        in_date,
                        create_date
                    )
                    VALUES (
                        %s,
                        %s,
                        %s,
                        0,
                        %s,
                        %s,
                        NOW(),
                        NOW()
                    )
                    RETURNING id
                """,
                    (product_id, lot_id, quantity, location_id, company_id),
                )
                # _logger.info(
                #     f"### data provided: product_id: {product_id}, lot_id: {lot_id}, quantity: {quantity}, location_id: {location_id}, company_id: {company_id}"
                # )
                quant_id = self.env.cr.fetchone()[0]
                changes.append(f"new lot: {lot_name}, location: {location_id}, qty:  → {quantity}")
                existing_quant_map[product_id].append(quant_id)

            if not lot_name:
                if (product_id, None, location_id) in stock_quant_mapping:
                    # Case 3: Update stock_quant for product without lot
                    _logger.info("### Case 3")

                    quant_id = stock_quant_mapping[(product_id, None, location_id)]
                    self.env.cr.execute(
                        """
                        UPDATE stock_quant
                        SET quantity = %s
                        WHERE id = %s
                    """,
                        (quantity, quant_id),
                    )
                    changes.append(f"no lot, loc: {location_id}, qty:  → {quantity}")
                    existing_quant_map[product_id].append(quant_id)

                    if quant_id and location_id == kardex_location_id:
                        existing_kardex_quants_ids_for_product.pop(quant_id)

                else:
                    # Case 4: Insert new stock_quant record for product with no lot which is not in stock quant
                    _logger.info("### lot_name: %s" % (lot_name,))
                    _logger.info("### Case 4")
                    if product_id:
                        self.env.cr.execute(
                            """
                            INSERT INTO stock_quant (
                                product_id,
                                lot_id,
                                quantity,
                                reserved_quantity,
                                location_id,
                                company_id,
                                in_date,
                                create_date
                            )
                            VALUES (
                                %s,
                                NULL,
                                %s,
                                0,
                                %s,
                                %s,
                                NOW(),
                                NOW()
                            )
                            RETURNING id
                        """,
                            (product_id, quantity, location_id, company_id),
                        )
                        quant_id = self.env.cr.fetchone()[0]
                        existing_quant_map[product_id].append(quant_id)
                        changes.append(f"no lot, location: {location_id}, qty:  → {quantity} (new)")

            if changes:
                self.env["kardex.sync.report.line"].create(
                    {
                        "report_id": report.id,
                        "product_id": product.id,
                        "changes": "\n".join(changes),
                    }
                )

        # quants not found in data coming from kardex
        _logger.info("existing quant map: %s" % (existing_quant_map,))
        for product_id, quant_ids in existing_quant_map.items():
            quants_without_kardex_data = self.env["stock.quant"].search(
                [("id", "not in", quant_ids), ("product_id", "=", product_id)]
            )
            _logger.info(f"quants_without_kardex_data: {quants_without_kardex_data}")

            # set quantity to zero for these quants
            quants_without_kardex_data.write({"quantity": 0})

        # remove quants for kardex which are not in data from ppg
        if existing_kardex_quants_ids_for_product and remove_quants:
            self.env["stock.quant"].browse(existing_kardex_quants_ids_for_product).unlink()

        # quants_without_kardex_data = existing_kardex_quants_for_product.filtered(lambda q: q.id not in kardex_quants)
        # _logger.info(f"quants_without_kardex_data: {quants_without_kardex_data}")

        # set quantity to zero for these quants
        # quants_without_kardex_data.write({'quantity': 0})

        # self._cr.commit()

        return True
