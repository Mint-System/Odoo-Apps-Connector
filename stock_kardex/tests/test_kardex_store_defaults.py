from contextlib import contextmanager
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase

from odoo.addons.base_kardex.models.base_kardex_mixin import BaseKardexMixin
from odoo.addons.stock_kardex.models.kardex_transfer_mixin import KardexTransferMixin


class TestKardexStoreDefaults(TransactionCase):
    """Defaulting and overriding the final location of Kardex Store moves.

    A Store move's line is sent to the SDB once its move's location_final_id is the
    Kardex location (kardex_transfer_mixin._get_transfer_type). stock.move.create/write
    decide what that ends up being: a computed default, or whatever the picker set.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        stock = cls.env.ref("stock.stock_location_stock")
        cls.shelf = cls.env["stock.location"].create({"name": "Regal", "location_id": stock.id, "usage": "internal"})
        cls.other_shelf = cls.env["stock.location"].create(
            {"name": "Anderes Regal", "location_id": stock.id, "usage": "internal"}
        )
        cls.kardex_loc = cls.env["stock.location"].create(
            {"name": "Kardex", "location_id": stock.id, "usage": "internal", "kardex": True}
        )
        cls.store_type = cls.env["stock.picking.type"].create(
            {
                "name": "Kardex Store Test",
                "code": "internal",
                "sequence_code": "KST",
                "kardex_picking_type": "kardex_store",
            }
        )
        cls.kardex_categ = cls.env["product.category"].create({"name": "Kardex Test Categ", "kardex": True})
        cls.plain_categ = cls.env["product.category"].create({"name": "Plain Test Categ", "kardex": False})

    def _make_product(self, categ, last_location=None):
        vals = {
            "name": "Store Test Product",
            "default_code": "STO.0001",
            "type": "consu",
            "is_storable": True,
            "kardex_product_id": 4712,
            "categ_id": categ.id,
            "uom_id": self.env.ref("uom.product_uom_unit").id,
        }
        if last_location:
            vals["last_location_id"] = last_location.id
        return self.env["product.product"].create(vals)

    @contextmanager
    def _sdb_connected(self):
        """Fake a working, connected SDB so send_to_kardex() runs all the way through."""
        with (
            patch.object(BaseKardexMixin, "_is_kardex_db_connected", return_value=True),
            patch.object(BaseKardexMixin, "_create_external_object", return_value=(5, "created", "updated", 900100)),
            patch.object(KardexTransferMixin, "_get_kardex_running_id", return_value=900100),
        ):
            yield

    def _make_move(self, product, location_final_id=None):
        picking = self.env["stock.picking"].create(
            {"picking_type_id": self.store_type.id, "location_id": self.shelf.id, "location_dest_id": self.shelf.id}
        )
        vals = {
            "name": product.name,
            "picking_id": picking.id,
            "picking_type_id": self.store_type.id,
            "product_id": product.id,
            "product_uom_qty": 1.0,
            "location_id": self.shelf.id,
            "location_dest_id": self.shelf.id,
        }
        if location_final_id is not None:
            vals["location_final_id"] = location_final_id.id
        with self._sdb_connected():
            move = self.env["stock.move"].create(vals)
            line = self.env["stock.move.line"].create(
                {
                    "move_id": move.id,
                    "picking_id": picking.id,
                    "product_id": product.id,
                    "quantity": 1.0,
                    "location_id": self.shelf.id,
                    "location_dest_id": self.shelf.id,
                }
            )
        return move, line

    def test_kardex_product_by_category_defaults_to_kardex_and_is_sent(self):
        product = self._make_product(self.kardex_categ)
        move, line = self._make_move(product)

        self.assertEqual(move.location_final_id, self.kardex_loc)
        self.assertTrue(line.kardex_done)

    def test_kardex_product_by_last_location_defaults_to_kardex_and_is_sent(self):
        product = self._make_product(self.plain_categ, last_location=self.kardex_loc)
        move, line = self._make_move(product)

        self.assertEqual(move.location_final_id, self.kardex_loc)
        self.assertTrue(line.kardex_done)

    def test_plain_product_is_not_defaulted_and_not_sent(self):
        product = self._make_product(self.plain_categ)
        move, line = self._make_move(product)

        self.assertNotEqual(move.location_final_id, self.kardex_loc)
        self.assertFalse(line.kardex_done)

    def test_explicit_final_location_is_never_overridden(self):
        """Rule: the computed default only applies when nothing else was given."""
        product = self._make_product(self.kardex_categ)
        move, line = self._make_move(product, location_final_id=self.other_shelf)

        self.assertEqual(move.location_final_id, self.other_shelf)
        self.assertFalse(line.kardex_done)

    def test_changing_final_location_afterwards_triggers_the_send(self):
        """Rule 3: a manual change to the Kardex location sends, independent of the product."""
        product = self._make_product(self.plain_categ)
        move, line = self._make_move(product, location_final_id=self.other_shelf)
        self.assertFalse(line.kardex_done)

        with self._sdb_connected():
            move.write({"location_final_id": self.kardex_loc.id})

        self.assertTrue(line.kardex_done)

    def test_already_sent_line_location_cannot_be_changed(self):
        product = self._make_product(self.kardex_categ)
        move, line = self._make_move(product)
        self.assertTrue(line.kardex_done)

        with self.assertRaises(UserError):
            move.write({"location_final_id": self.other_shelf.id})

    def test_writing_the_same_final_location_on_a_sent_line_does_not_raise(self):
        product = self._make_product(self.kardex_categ)
        move, line = self._make_move(product)
        self.assertTrue(line.kardex_done)

        move.write({"location_final_id": self.kardex_loc.id})  # unchanged value, must not raise
