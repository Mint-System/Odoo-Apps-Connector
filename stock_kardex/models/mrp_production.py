import logging

from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)


class MrpProduction(models.Model):
    _name = "mrp.production"
    _inherit = ["validation.mixin", "mrp.production"]
    _description = "Kardex MRP Production"

    kardex = fields.Boolean(compute="_compute_kardex", store=True)

    @api.depends("product_id.product_tmpl_id.kardex")
    def _compute_kardex(self):
        for record in self:
            # Check if the related product template's kardex field is True
            record.kardex = record.product_id.product_tmpl_id.kardex

    
