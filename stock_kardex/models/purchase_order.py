import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class PurchaseOrder(models.Model):
    _name = "purchase.order"
    _inherit = ["validation.mixin", "purchase.order", "base.kardex.mixin"]
    _description = "Purchase Kardex Order"

    kardex = fields.Boolean(default=False, compute="_compute_kardex", store=True)

    @api.depends("order_line.product_id.kardex")
    def _compute_kardex(self):
        for order in self:
            order.kardex = any(line.product_id.kardex for line in order.order_line)


# class PurchaseOrderLine(models.Model):
#     _inherit = 'purchase.order.line'

#     @api.model
#     def create(self, vals):
#         line = super().create(vals)
#         if line.order_id:
#             line.order_id._compute_kardex()
#         return line

#     def write(self, vals):
#         res = super().write(vals)
#         for line in self:
#             if line.order_id:
#                 line.order_id._compute_kardex()
#         return res
