from unittest.mock import patch

from odoo.tests.common import TransactionCase

from odoo.addons.base_kardex.models.base_kardex_mixin import BaseKardexMixin

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
            "MengeGesamt": 5.0,
            "MengeAuftrag": 5.0,
            "BelegKomplett": 2,
            "id_list": "101, 102",
        }
        row.update(overrides)
        return row

    def _sync(self, *answers, picking=None):
        """Run the sync; every entry of ``answers`` is what the SDB returns for one poll."""
        pickings = picking or self.env["stock.picking"]
        with patch.object(BaseKardexMixin, "_execute_query_on_mssql", side_effect=list(answers)) as query:
            for _answer in answers:
                pickings.sync_pickings()
        return query

    def test_journal_entries_are_unique(self):
        journal = self.env["stock.picking.journal"]
        first = journal.create({"journal_id": 101, "kardex_running_id": 1})
        again = journal.create({"journal_id": 101, "kardex_running_id": 2})
        self.assertEqual(first, again)
        self.assertEqual(again.kardex_running_id, 2)

    def test_complete_answer_updates_line_and_picking(self):
        picking, line = self._make_line(qty=5.0)
        query = self._sync([self._journal_row(picking, line, MengeErledigt=4.0, MengeGesamt=4.0)])

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

    def test_partial_answers_keep_the_line_open_until_complete(self):
        picking, line = self._make_line(qty=5.0)
        partial = self._journal_row(
            picking, line, MengeErledigt=2.0, MengeGesamt=2.0, MaxKomplett=1, BelegKomplett=1, id_list="101"
        )
        rest = self._journal_row(picking, line, MengeErledigt=3.0, MengeGesamt=5.0, id_list="102")

        self._sync([partial])
        self.assertEqual(line.quantity, 2.0)
        self.assertEqual(line.kardex_status, "2", "still waiting for the rest")
        self.assertFalse(line.kardex_sync)
        self.assertEqual(picking.kardex_status, "1")

        self._sync([rest])
        self.assertEqual(line.kardex_status, "4")
        self.assertTrue(line.kardex_sync)
        self.assertEqual(sorted(picking.move_line_ids.mapped("quantity")), [2.0, 3.0])
        self.assertEqual(picking.kardex_status, "2")
        self.assertEqual(self.env["stock.picking.journal"].search([]).mapped("journal_id"), [101, 102])

    def test_document_closed_by_kardex_completes_a_short_delivery(self):
        picking, line = self._make_line(qty=5.0)
        self._sync([self._journal_row(picking, line, MengeErledigt=3.0, MengeGesamt=3.0, BelegKomplett=2)])

        self.assertEqual(line.kardex_status, "4")

    def test_unknown_lot_is_retried_instead_of_lost(self):
        picking, line = self._make_line(tracking="lot")
        row = self._journal_row(picking, line, SerienOrCharge="LOT-9")

        with patch("odoo.addons.stock_kardex.models.stock_move_line.LOT_POLICY", {"3": (True, False)}):
            self._sync([row])
        self.assertEqual(line.kardex_status, "2")
        self.assertFalse(self.env["stock.picking.journal"].search([]), "row must be read again next time")

        self.env["stock.lot"].create({"name": "LOT-9", "product_id": line.product_id.id})
        with patch("odoo.addons.stock_kardex.models.stock_move_line.LOT_POLICY", {"3": (True, False)}):
            self._sync([row])
        self.assertEqual(line.lot_id.name, "LOT-9")
        self.assertEqual(line.kardex_status, "4")

    def test_sync_of_one_picking_leaves_others_alone(self):
        picking, line = self._make_line()
        other_picking, other_line = self._make_line()
        other_line.kardex_running_id = "900002"

        query = self._sync([self._journal_row(picking, line)], picking=picking)

        self.assertEqual(query.call_count, 1)
        self.assertEqual(line.kardex_status, "4")
        self.assertEqual(other_line.kardex_status, "2")

    def _sync_status(self, sdb_row):
        with patch.object(BaseKardexMixin, "_execute_query_on_mssql", return_value=sdb_row):
            self.env["stock.picking"].sync_status()

    def test_order_fetched_by_kardex_is_marked(self):
        picking, line = self._make_line()
        line.kardex_status = "1"
        self._sync_status({"Status": 2, "Row_Update_Time": "Mär 21 2024  3:49PM"})

        self.assertEqual(line.kardex_status, "2")
        self.assertEqual(line.kardex_row_update_time, "Mär 21 2024  3:49PM")

    def test_order_not_yet_fetched_stays_pending(self):
        picking, line = self._make_line()
        line.kardex_status = "1"
        self._sync_status({"Status": 1, "Row_Update_Time": None})

        self.assertEqual(line.kardex_status, "1")

    def test_status_unknown_to_odoo_is_ignored(self):
        picking, line = self._make_line()
        line.kardex_status = "1"
        self._sync_status({"Status": 9, "Row_Update_Time": "Mär 21 2024  3:49PM"})

        self.assertEqual(line.kardex_status, "1")
