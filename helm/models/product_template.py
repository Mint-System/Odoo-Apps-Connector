from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    chart_ids = fields.Many2many("helm.chart")
