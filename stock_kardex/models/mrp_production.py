
import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class MrpProduction(models.Model):
    _inherit = ['mrp.production']
    _description = 'Kardex MRP Production'

    kardex = fields.Boolean(string='Kardex', compute='_compute_kardex', store=True)

    @api.depends('product_id.product_tmpl_id.kardex')
    def _compute_kardex(self):
        for record in self:
            # Check if the related product template's kardex field is True
            record.kardex = record.product_id.product_tmpl_id.kardex

