from unittest.mock import patch

from odoo.addons.base_kardex.models.base_kardex_mixin import BaseKardexMixin
from odoo.tests.common import TransactionCase


class TestSendToKardex(TransactionCase):
    """Odoo side of a Kardex order: which lines are sent and what the SDB row contains.

    The SDB is replaced by mocks, so no MSSQL connection is needed.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        stock = cls.env.ref("stock.stock_location_stock")
        cls.customers = cls.env.ref("stock.stock_location_customers")
        cls.kardex = cls.env["stock.location"].create({"name": "Kardex", "location_id": stock.id, "usage": "internal"})
        cls.shelf = cls.env["stock.location"].create({"name": "Regal", "location_id": stock.id, "usage": "internal"})

    def _make_line(self, kardex_type, source, dest, final=None, tracking="none", with_lot=False):
        picking_type = self.env["stock.picking.type"].search([("kardex_picking_type", "=", kardex_type)])
        if not picking_type:
            picking_type = self.env["stock.picking.type"].create(
                {
                    "name": kardex_type,
                    "code": "internal",
                    "sequence_code": kardex_type[-4:].upper(),
                    "kardex_picking_type": kardex_type,
                }
            )
        product = self.env["product.product"].create(
            {
                "name": "Kardex Test Product",
                "default_code": "TST.0001",
                "type": "consu",
                "is_storable": True,
                "tracking": tracking,
                "kardex_product_id": 4711,
                "uom_id": self.env.ref("uom.product_uom_unit").id,
            }
        )
        picking = self.env["stock.picking"].create(
            {"picking_type_id": picking_type.id, "location_id": source.id, "location_dest_id": dest.id}
        )
        move = self.env["stock.move"].create(
            {
                "name": product.name,
                "picking_id": picking.id,
                "product_id": product.id,
                "product_uom_qty": 3.0,
                "location_id": source.id,
                "location_dest_id": dest.id,
                "location_final_id": (final or dest).id,
            }
        )
        vals = {
            "move_id": move.id,
            "picking_id": picking.id,
            "product_id": product.id,
            "quantity": 3.0,
            "location_id": source.id,
            "location_dest_id": dest.id,
        }
        if with_lot:
            vals["lot_id"] = self.env["stock.lot"].create({"name": "LOT-7", "product_id": product.id}).id
        return self.env["stock.move.line"].create(vals)

    def test_line_leaving_kardex_is_a_get_order(self):
        line = self._make_line("kardex_get", self.kardex, self.customers, tracking="lot", with_lot=True)

        self.assertEqual(line._get_transfer_type(), "get")
        vals = line._prepare_sdb_order_vals("get", 900001)
        self.assertEqual(vals["kardex_direction"], 4)
        self.assertEqual(vals["kardex_quantity"], 3.0)
        self.assertEqual(vals["kardex_doc_number"], line.picking_id.name)
        self.assertEqual(vals["kardex_product_id"], 4711)
        self.assertEqual(vals["kardex_running_id"], 900001)
        self.assertEqual(vals["kardex_status"], "1")
        self.assertIsNone(vals["kardex_charge"], "lots are not sent when taking stock out")

    def test_store_into_kardex_sends_lot_as_charge(self):
        line = self._make_line("kardex_store", self.shelf, self.shelf, final=self.kardex, tracking="lot", with_lot=True)

        self.assertEqual(line._get_transfer_type(), "store")
        vals = line._prepare_sdb_order_vals("store", 900002)
        self.assertEqual(vals["kardex_direction"], 3)
        self.assertEqual(vals["kardex_charge"], "LOT-7")
        self.assertIsNone(vals["kardex_serial"])

    def test_store_into_kardex_sends_serial(self):
        line = self._make_line(
            "kardex_store", self.shelf, self.shelf, final=self.kardex, tracking="serial", with_lot=True
        )

        vals = line._prepare_sdb_order_vals("store", 900003)
        self.assertEqual(vals["kardex_serial"], "LOT-7")
        self.assertIsNone(vals["kardex_charge"])

    def test_postproduction_into_kardex_is_stored(self):
        line = self._make_line("kardex_postprod", self.shelf, self.kardex)

        self.assertEqual(line._get_transfer_type(), "postproduction")
        self.assertEqual(line._prepare_sdb_order_vals("postproduction", 1)["kardex_direction"], 3)

    def test_lines_not_touching_kardex_are_not_sent(self):
        get_elsewhere = self._make_line("kardex_get", self.shelf, self.customers)
        store_elsewhere = self._make_line("kardex_store", self.shelf, self.shelf, final=self.shelf)

        self.assertFalse(get_elsewhere._get_transfer_type())
        self.assertFalse(store_elsewhere._get_transfer_type())

    def test_line_is_sent_only_once(self):
        line = self._make_line("kardex_get", self.kardex, self.customers)

        with (
            patch.object(BaseKardexMixin, "_is_kardex_db_connected", return_value=True),
            patch.object(type(line), "_get_kardex_running_id", return_value=900004),
            patch.object(
                BaseKardexMixin, "_create_external_object", return_value=(5, "created", "updated", 900004)
            ) as create,
        ):
            line.send_to_kardex()
            line.send_to_kardex()

        self.assertEqual(create.call_count, 1)
        self.assertTrue(line.kardex_done)
        self.assertEqual(line.kardex_running_id, "900004")
        self.assertEqual(line.kardex_status, "1")
        self.assertEqual(line.picking_id.kardex_picking_state, "waiting_for_kardex")
        self.assertTrue(line.picking_id.kardex_done, "the picking shows that it is known in Kardex")

    def test_nothing_is_sent_without_sdb_connection(self):
        line = self._make_line("kardex_get", self.kardex, self.customers)

        with patch.object(BaseKardexMixin, "_create_external_object") as create:
            line.send_to_kardex()

        create.assert_not_called()
        self.assertFalse(line.kardex_done)
