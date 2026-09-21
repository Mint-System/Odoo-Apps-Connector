from unittest.mock import patch

from odoo.addons.base_kardex.models.base_kardex_mixin import BaseKardexMixin
from odoo.tests.common import TransactionCase

BZID = "900001"


class TestJournalSync(TransactionCase):
    """Odoo side of the SDB answer: PPG_Journal rows are turned into picking updates.

    The SDB is replaced by fixture rows, so no MSSQL connection is needed.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.stock = cls.env.ref("stock.stock_location_stock")
        cls.customers = cls.env.ref("stock.stock_location_customers")

    def _make_line(self, tracking="none", qty=5.0):
        product = self.env["product.product"].create(
            {
                "name": "Kardex Test Product",
                "default_code": "TST.0001",
                "type": "consu",
                "is_storable": True,
                "tracking": tracking,
            }
        )
        picking = self.env["stock.picking"].create(
            {
                "picking_type_id": self.env.ref("stock.picking_type_out").id,
                "location_id": self.stock.id,
                "location_dest_id": self.customers.id,
            }
        )
        move = self.env["stock.move"].create(
            {
                "name": product.name,
                "picking_id": picking.id,
                "product_id": product.id,
                "product_uom_qty": qty,
                "location_id": self.stock.id,
                "location_dest_id": self.customers.id,
            }
        )
        line = self.env["stock.move.line"].create(
            {
                "move_id": move.id,
                "picking_id": picking.id,
                "product_id": product.id,
                "quantity": qty,
                "location_id": self.stock.id,
                "location_dest_id": self.customers.id,
                "kardex_running_id": BZID,
                "kardex_status": "2",
            }
        )
        return picking, line

    def _journal_row(self, picking, line, **overrides):
        row = {
            "BzId": int(BZID),
            "Belegnummer": picking.name,
            "SerienOrCharge": "__none__",
            "Suchbegriff": line.product_id.default_code,
            "Richtung": "3",
            "Row_Create_Time": "Mär 21 2024  3:49PM",
            "Row_Update_Time": "Mär 21 2024  3:49PM",
            "MengeErledigt": 5.0,
            "MaxKomplett": 2,
            "id_list": "101, 102",
        }
        row.update(overrides)
        return row

    def _sync(self, rows):
        with patch.object(BaseKardexMixin, "_execute_query_on_mssql", return_value=rows) as query:
            self.env["stock.picking"].sync_pickings()
        return query

    def test_journal_entries_are_unique(self):
        journal = self.env["stock.picking.journal"]
        first = journal.create({"journal_id": 101, "kardex_running_id": 1})
        again = journal.create({"journal_id": 101, "kardex_running_id": 2})
        self.assertEqual(first, again)
        self.assertEqual(again.kardex_running_id, 2)

    def test_complete_answer_updates_line_and_picking(self):
        picking, line = self._make_line(qty=5.0)
        query = self._sync([self._journal_row(picking, line, MengeErledigt=4.0)])

        self.assertEqual(line.quantity, 4.0)
        self.assertEqual(line.kardex_status, "4")
        self.assertTrue(line.kardex_sync)
        self.assertEqual(picking.kardex_status, "2")
        self.assertTrue(picking.kardex_sync)
        self.assertEqual(
            self.env["stock.picking.journal"].search([]).mapped("journal_id"),
            [101, 102],
        )
        self.assertIn("NOT IN", query.call_args.args[1], "processed journal ids must be excluded")

    def test_untracked_product_gets_no_lot(self):
        picking, line = self._make_line(tracking="none")
        self._sync([self._journal_row(picking, line)])

        self.assertFalse(line.lot_id)
        self.assertFalse(self.env["stock.lot"].search([("name", "=", "__none__")]))

    def test_lot_from_answer_is_created_and_assigned(self):
        picking, line = self._make_line(tracking="lot")
        self._sync([self._journal_row(picking, line, SerienOrCharge="LOT-42")])

        self.assertEqual(line.lot_id.name, "LOT-42")
        self.assertEqual(line.lot_id.product_id, line.product_id)

    def test_second_lot_creates_additional_line(self):
        picking, line = self._make_line(tracking="lot", qty=5.0)
        self._sync(
            [
                self._journal_row(picking, line, SerienOrCharge="LOT-1", MengeErledigt=3.0, id_list="101"),
                self._journal_row(picking, line, SerienOrCharge="LOT-2", MengeErledigt=2.0, id_list="102"),
            ]
        )

        lines = picking.move_line_ids
        self.assertEqual(sorted(lines.mapped("lot_id.name")), ["LOT-1", "LOT-2"])
        self.assertEqual(sum(lines.mapped("quantity")), 5.0)
