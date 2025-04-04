from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    helm_repo_id = fields.Many2one("helm.repo")
