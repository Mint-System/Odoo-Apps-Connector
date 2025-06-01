import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _name = "sale.order"
    _inherit = ["sale.order", "base.kardex.mixin"]
    _description = "Sale Kardex Order"

    kardex = fields.Boolean(default=False, compute="_compute_kardex", store=True)

    @api.depends("order_line.product_id.kardex")
    def _compute_kardex(self):
        for order in self:
            order.kardex = any(line.product_id.kardex for line in order.order_line)

    def action_confirm(self):
        for order in self:
            # check if picking types with kardex_picking_type = store exist
            store_picking_type = self.env["stock.picking.type"].search([("kardex_picking_type", "=", "kardex_get")])
            if not store_picking_type:
                raise UserError(
                    _(
                        "There is no picking type associated to kardex picking type = kardex_get. Please correct this in the configuration."
                    )
                )

        # If validation passes, continue with standard confirmation
        return super().action_confirm()


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    @api.onchange("product_id")
    def _onchange_product_id_custom(self):
        if self.product_id:
            # Access the product.template
            product_template = self.product_id.product_tmpl_id
            self.env["stock.quant"].sync_stocks(product_template.default_code)
