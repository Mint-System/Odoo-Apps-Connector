from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    chart_id = fields.Many2one("helm.chart")
