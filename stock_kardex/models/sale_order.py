import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _name = "sale.order"
    _inherit = ["validation.mixin", "sale.order", "base.kardex.mixin"]
    _description = "Sale Kardex Order"

    kardex = fields.Boolean(default=False, compute="_compute_kardex", store=True)

    @api.depends("order_line.product_id.kardex")
    def _compute_kardex(self):
        for order in self:
            order.kardex = any(line.product_id.kardex for line in order.order_line)


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    @api.onchange("product_id")
    def _onchange_product_id_custom(self):
        if self.product_id:
            # Access the product.template
            product_template = self.product_id.product_tmpl_id
            # self.env["stock.quant"].sync_stocks(product_template.default_code)
