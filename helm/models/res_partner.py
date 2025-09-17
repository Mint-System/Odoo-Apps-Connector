from odoo import fields, models


class Partner(models.Model):
    _inherit = "res.partner"

    helm_product_ids = fields.Many2many("product.product")
