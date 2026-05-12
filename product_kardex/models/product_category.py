import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class ProductCategory(models.Model):
    _name = "product.category"
    _inherit = ["product.category"]

    kardex = fields.Boolean(default=False)
    parent_id_name = fields.Char(related="parent_id.name")
    abbr = fields.Char(string="Abbreviation")
    is_storable = fields.Boolean(default=True)
