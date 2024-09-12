import logging
import ast

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class MrpBom(models.Model):
    _inherit = ['mrp.bom']
    _description = 'Kardex BoM'

    kardex = fields.Boolean(string='Kardex', compute="_compute_kardex", store=True)
    # perhaps another option: override type field?
    # type = fields.Selection(selection_add=[
    #    ('kardex', 'Kardex') 
    # ], ondelete={'kardex': 'set default'})


    @api.depends('product_tmpl_id.kardex')
    def _compute_kardex(self):
        for bom in self:
            bom.kardex = bom.product_tmpl_id.kardex

    def send_to_kardex(self):
        pass


class MrpBomLine(models.Model):
    _inherit = ['mrp.bom.line']
    # not needed
    # TODO: delete this field
    products_domain = fields.Binary(string="products domain", help="Dynamic domain used for the products that can be chosen on a move line", compute="_compute_products_domain")
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        domain="[('kardex', '=', parent.kardex)]",
    ) # this adds domain to existing domain!

   
    # complicated domain setting
    # does override existing domain
    # TODO: delete
    @api.depends('bom_id.product_tmpl_id')
    def _compute_products_domain(self):
        # if picking is kardex than product must be kardex too
        # could also be done by onchange but dynamic domain setting by onchange method seems to deprecated in odoo 17
        # field products_domain must be included in view
        
        for obj in self:
            if obj.bom_id.product_tmpl_id:  
                kardex_boolean = obj.bom_id.product_tmpl_id.kardex
                obj.products_domain = [('kardex', '=', kardex_boolean)]
            else:
                # Existing domain to all products if no product template is set in BOM
                obj.products_domain = []
        




