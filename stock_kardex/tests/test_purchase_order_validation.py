from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestPurchaseOrderPickingTypeValidation(TransactionCase):
    def setUp(self):
        super().setUp()
        # Create a vendor
        self.partner = self.env["res.partner"].create(
            {
                "name": "Test Vendor",
                "supplier_rank": 1,
            }
        )

        # Create a product
        self.product = self.env["product.product"].create(
            {
                "name": "Test Product",
                "type": "product",
                "purchase_ok": True,
                "uom_id": self.env.ref("uom.product_uom_unit").id,
            }
        )

    def test_invalid_picking_type_raises_error(self):
        # Create a picking type for receipts (incoming) without required field
        self.picking_type_invalid = self.env["stock.picking.type"].create(
            {
                "name": "Invalid Receipt",
                "code": "incoming",
                "sequence_code": "I",
                "kardex_picking_type": "",  # Not 'kardex_store'
            }
        )
        po = self.env["purchase.order"].create(
            {
                "partner_id": self.partner.id,
                "order_line": [
                    (
                        0,
                        0,
                        {
                            "name": "Test line",
                            "product_id": self.product.id,
                            "product_qty": 1.0,
                            "product_uom": self.product.uom_id.id,
                            "price_unit": 10.0,
                        },
                    )
                ],
            }
        )

        with self.assertRaises(UserError):
            po.button_confirm()

    def test_valid_picking_type_allows_confirmation(self):
        # Create a valid picking type
        self.picking_type_valid = self.env["stock.picking.type"].create(
            {
                "name": "Valid Receipt",
                "code": "incoming",
                "sequence_code": "V",
                "kardex_picking_type": "kardex_store",
            }
        )

        po = self.env["purchase.order"].create(
            {
                "partner_id": self.partner.id,
                "order_line": [
                    (
                        0,
                        0,
                        {
                            "name": "Valid line",
                            "product_id": self.product.id,
                            "product_qty": 1.0,
                            "product_uom": self.product.uom_id.id,
                            "price_unit": 10.0,
                        },
                    )
                ],
            }
        )

        po.button_confirm()
        self.assertEqual(po.state, "purchase")
