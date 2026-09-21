from unittest.mock import patch

from odoo.exceptions import AccessError, UserError
from odoo.tests.common import TransactionCase

from odoo.addons.base_kardex.models.base_kardex_mixin import BaseKardexMixin

BZID = "900001"


class FakeSdb:
    """Stands in for the SDB: answers the reads of the wizard and records what is written."""

    def __init__(self, qty):
        self.order = {
            "ID": 1,
            "Belegnummer": "WH/OUT/0001",
            "ArtikelID": 4711,
            "Richtung": 4,
            "Menge": qty,
            "Status": 1,
            "Suchbegriff": "TST.0001",
        }
        self.writes = []

    def __call__(self, query_type, sql, *params):
        if query_type == "select_one":
            return dict(self.order) if "FROM PPG_Auftraege" in sql else {"reported": None}
        if query_type == "select":
            return []
        self.writes.append((query_type, sql, params[0]))
        return 1

    def journal_rows(self):
        return [params for query_type, sql, params in self.writes if "INTO PPG_Journal" in sql]


class TestKardexSimulator(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.connection = cls.env["base.external.mssql"].create(
            {
                "name": "Kardex test",
                "server": "localhost",
                "database": "SchnittstellenDB",
                "username": "odoo",
                "password": "secret",
                "priority": True,
                "allow_simulation": True,
            }
        )
        cls.manager = cls.env.ref("base.user_admin")

    def _make_picking(self, tracking="lot", qty=3.0):
        stock = self.env.ref("stock.stock_location_stock")
        customers = self.env.ref("stock.stock_location_customers")
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
                "location_id": stock.id,
                "location_dest_id": customers.id,
            }
        )
        move = self.env["stock.move"].create(
            {
                "name": product.name,
                "picking_id": picking.id,
                "product_id": product.id,
                "product_uom_qty": qty,
                "location_id": stock.id,
                "location_dest_id": customers.id,
            }
        )
        self.env["stock.move.line"].create(
            {
                "move_id": move.id,
                "picking_id": picking.id,
                "product_id": product.id,
                "quantity": qty,
                "location_id": stock.id,
                "location_dest_id": customers.id,
                "kardex_running_id": BZID,
                "kardex_status": "1",
            }
        )
        return picking

    def _simulate(self, tracking="lot", qty=3.0, scenario="complete"):
        picking = self._make_picking(tracking, qty)
        sdb = FakeSdb(qty)
        wizard_model = self.env["kardex.simulator.wizard"].with_user(self.manager)
        with patch.object(BaseKardexMixin, "_execute_query_on_mssql", side_effect=sdb):
            wizard = wizard_model.with_context(default_picking_id=picking.id, default_scenario=scenario).create({})
            wizard.action_simulate_answer()
        return picking, sdb

    def test_simulation_is_refused_on_a_connection_that_does_not_allow_it(self):
        self.connection.allow_simulation = False
        picking = self._make_picking()
        sdb = FakeSdb(3.0)
        wizard_model = self.env["kardex.simulator.wizard"].with_user(self.manager)
        with patch.object(BaseKardexMixin, "_execute_query_on_mssql", side_effect=sdb):
            wizard = wizard_model.with_context(default_picking_id=picking.id).create({})
            with self.assertRaises(UserError):
                wizard.action_simulate_answer()
        self.assertFalse(sdb.writes)

    def test_only_inventory_managers_may_use_the_simulator(self):
        picking = self._make_picking()
        worker = self.env["res.users"].create(
            {"name": "Worker", "login": "worker", "groups_id": [(6, 0, [self.env.ref("stock.group_stock_user").id])]}
        )
        with patch.object(BaseKardexMixin, "_execute_query_on_mssql", side_effect=FakeSdb(3.0)):
            with self.assertRaises(AccessError):
                self.env["kardex.simulator.wizard"].with_user(worker).with_context(
                    default_picking_id=picking.id
                ).create({})

    def test_complete_answer_marks_order_fetched_and_reports_it(self):
        picking, sdb = self._simulate(tracking="lot", qty=3.0)

        updates = [write for write in sdb.writes if write[0] == "update"]
        self.assertEqual(len(updates), 1)
        self.assertIn("Status = 2", updates[0][1])
        self.assertEqual(updates[0][2], (900001,))

        (row,) = sdb.journal_rows()
        journal = dict(
            zip(
                (
                    "STATUS",
                    "Belegnummer",
                    "Artikelid",
                    "Charge",
                    "Seriennummer",
                    "Menge",
                    "Richtung",
                    "Komplett",
                    "BzId",
                    "Suchbegriff",
                ),
                row,
                strict=True,
            )
        )
        self.assertEqual(journal["Charge"], "SIM-900001")
        self.assertIsNone(journal["Seriennummer"])
        self.assertEqual(journal["Menge"], 3.0)
        self.assertEqual(journal["Komplett"], 2)
        self.assertEqual(journal["Richtung"], "4")
        self.assertEqual(journal["Belegnummer"], "WH/OUT/0001")
        self.assertEqual(journal["Artikelid"], 4711)
        self.assertIn("Kardex answer simulated", picking.message_ids[0].body)

    def test_serial_products_get_one_row_per_serial(self):
        _picking, sdb = self._simulate(tracking="serial", qty=3.0)

        rows = sdb.journal_rows()
        self.assertEqual([row[4] for row in rows], ["SIM-900001-1", "SIM-900001-2", "SIM-900001-3"])
        self.assertEqual([row[5] for row in rows], [1.0, 1.0, 1.0])
        self.assertEqual([row[7] for row in rows], [1, 1, 2], "only the last row closes the document")

    def test_partial_answer_does_not_close_the_document(self):
        _picking, sdb = self._simulate(tracking="none", qty=4.0, scenario="partial")

        (row,) = sdb.journal_rows()
        self.assertEqual(row[5], 2.0)
        self.assertEqual(row[7], 1)
