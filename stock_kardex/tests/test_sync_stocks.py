from unittest.mock import patch

from odoo.tests.common import TransactionCase

from odoo.addons.base_kardex.models.base_kardex_mixin import BaseKardexMixin
from odoo.addons.stock_kardex.models.stock_quant import StockQuant


class TestSyncStocks(TransactionCase):
    """The Odoo quants of the Kardex location follow the stock reported by the ProdDB."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        stock = cls.env.ref("stock.stock_location_stock")
        cls.env["stock.location"].search(["|", ("kardex", "=", True), ("palette", "=", True)]).write(
            {"kardex": False, "palette": False}
        )
        cls.kardex = cls.env["stock.location"].create(
            {"name": "Kardex", "location_id": stock.id, "usage": "internal", "kardex": True}
        )
        cls.palette = cls.env["stock.location"].create(
            {"name": "Paletten", "location_id": stock.id, "usage": "internal", "palette": True}
        )
        cls.product = cls.env["product.product"].create(
            {"name": "Sync Product", "default_code": "TST.SYNC", "is_storable": True}
        )
        cls.lot_product = cls.env["product.product"].create(
            {"name": "Sync Lot Product", "default_code": "TST.LOT", "is_storable": True, "tracking": "lot"}
        )
        cls.env["ir.config_parameter"].sudo().set_param("kardex.inv_method", "direct")

    def _sync(self, rows, **kwargs):
        materials = [{"Suchbegriff": code} for code in ("TST.SYNC", "TST.LOT")]
        with (
            patch.object(BaseKardexMixin, "_is_proddb_connected", return_value=True),
            patch.object(BaseKardexMixin, "_is_kardex_db_connected", return_value=False),
            patch.object(StockQuant, "_get_data_direct_call", return_value=(materials, rows)),
        ):
            return self.env["stock.quant"].sync_stocks(**kwargs)

    def _row(self, code, qty, location="Shuttle-01", lot=None, serial=None):
        return {"Suchbegriff": code, "Bestand": qty, "LocationName": location, "Charge": lot, "Seriennummer": serial}

    def _kardex_qty(self, product, location=None):
        quants = self.env["stock.quant"].search(
            [("product_id", "=", product.id), ("location_id", "=", (location or self.kardex).id)]
        )
        return sum(quants.mapped("quantity"))

    def test_kardex_stock_is_summed_per_lot(self):
        self.env["stock.quant"]._update_available_quantity(self.product, self.kardex, 3)
        rows = [
            self._row("TST.SYNC", 4),
            self._row("TST.SYNC", 2, location="Shuttle-02"),
            self._row("TST.LOT", 5, lot="L1"),
        ]

        self.assertTrue(self._sync(rows, all_products=True))

        self.assertEqual(self._kardex_qty(self.product), 6)
        lot = self.env["stock.lot"].search([("name", "=", "L1"), ("product_id", "=", self.lot_product.id)])
        self.assertEqual(len(lot), 1)
        self.assertEqual(self._kardex_qty(self.lot_product), 5)
        self.assertEqual(self.product.last_location_id, self.kardex)

    def test_existing_lot_is_reused(self):
        lot = self.env["stock.lot"].create({"name": "L1", "product_id": self.lot_product.id})

        self._sync([self._row("TST.LOT", 2, lot="L1")], all_products=True)

        quant = self.env["stock.quant"].search(
            [("product_id", "=", self.lot_product.id), ("location_id", "=", self.kardex.id)]
        )
        self.assertEqual(quant.lot_id, lot)
        self.assertEqual(quant.quantity, 2)

    def test_material_without_stock_is_set_to_zero(self):
        self.env["stock.quant"]._update_available_quantity(self.product, self.kardex, 3)

        self._sync([self._row("TST.LOT", 1, lot="L1")], all_products=True)

        self.assertEqual(self._kardex_qty(self.product), 0)

    def test_other_locations_only_with_all_locations(self):
        self.env["ir.config_parameter"].sudo().set_param("kardex.aggregate_palettes", "True")
        rows = [self._row("TST.SYNC", 4), self._row("TST.SYNC", 8, location="Palette-07")]

        self._sync(rows, all_products=True)
        self.assertEqual(self._kardex_qty(self.product, self.palette), 0)

        self._sync(rows, all_products=True, all_locations=True)
        self.assertEqual(self._kardex_qty(self.product, self.palette), 8)
        self.assertEqual(self._kardex_qty(self.product), 4)
