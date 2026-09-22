from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestKardexPickingTypeValidation(TransactionCase):
    """Orders with Kardex products need the Kardex picking types to be configured."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env["res.partner"].create({"name": "Test Partner"})
        kardex_categ = cls.env["product.category"].create({"name": "Kardex Test Category", "kardex": True})
        plain_categ = cls.env["product.category"].create({"name": "Plain Test Category", "kardex": False})
        cls.kardex_product = cls._make_product("Kardex Product", kardex_categ)
        cls.plain_product = cls._make_product("Plain Product", plain_categ)

    @classmethod
    def _make_product(cls, name, categ):
        # "kardex" is computed from the category (and the last location); it cannot be set directly
        return cls.env["product.product"].create(
            {
                "name": name,
                "type": "consu",
                "is_storable": True,
                "purchase_ok": True,
                "sale_ok": True,
                "categ_id": categ.id,
                "uom_id": cls.env.ref("uom.product_uom_unit").id,
            }
        )

    def _purchase_order(self, product):
        return self.env["purchase.order"].create(
            {
                "partner_id": self.partner.id,
                "order_line": [
                    (0, 0, {"name": product.name, "product_id": product.id, "product_qty": 1.0, "price_unit": 10.0})
                ],
            }
        )

    def _sale_order(self, product):
        return self.env["sale.order"].create(
            {
                "partner_id": self.partner.id,
                "order_line": [(0, 0, {"product_id": product.id, "product_uom_qty": 1.0, "price_unit": 10.0})],
            }
        )

    def _kardex_picking_type(self, kardex_picking_type, code):
        return self.env["stock.picking.type"].create(
            {
                "name": kardex_picking_type,
                "code": code,
                "sequence_code": kardex_picking_type[-4:].upper(),
                "kardex_picking_type": kardex_picking_type,
            }
        )

    def test_purchase_of_kardex_product_needs_store_picking_type(self):
        po = self._purchase_order(self.kardex_product)
        with self.assertRaises(UserError):
            po.button_confirm()

        self._kardex_picking_type("kardex_store", "internal")
        po.button_confirm()
        self.assertEqual(po.state, "purchase")

    def test_purchase_of_plain_product_is_not_blocked(self):
        po = self._purchase_order(self.plain_product)
        po.button_confirm()
        self.assertEqual(po.state, "purchase")

    def test_sale_of_kardex_product_needs_get_picking_type(self):
        so = self._sale_order(self.kardex_product)
        with self.assertRaises(UserError):
            so.action_confirm()

        self._kardex_picking_type("kardex_get", "outgoing")
        so.action_confirm()
        self.assertEqual(so.state, "sale")

    def test_sale_of_plain_product_is_not_blocked(self):
        so = self._sale_order(self.plain_product)
        so.action_confirm()
        self.assertEqual(so.state, "sale")
