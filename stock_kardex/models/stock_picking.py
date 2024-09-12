import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class StockPicking(models.Model):
    _inherit = ['stock.picking']
    _description = 'Stock Kardex Picking'

    kardex = fields.Boolean(string='Kardex', default=False)

    def send_to_kardex(self):
        pass

    

class StockMove(models.Model):
    _inherit = ['stock.move']
    products_domain = fields.Binary(string="products domain", help="Dynamic domain used for the products that can be chosen on a move line", compute="_compute_products_domain")
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        domain="[('kardex', '=', parent.kardex)]",
    ) # this adds domain to existing domain!


    @api.depends('picking_id.kardex')
    def _compute_products_domain(self):
        # if picking is kardex than product must be kardex too
        # could also be done by onchange but dynamic domain setting by onchange method seems to deprecated in odoo 17
        # field products_domain must be included in view
        _logger.info('compute method called')
        for obj in self:
            if obj.picking_id.kardex:
                domain = [('kardex', '=', 'True')]
            else:
                domain = []

            obj.products_domain = domain


    # @api.onchange('kardex')
    # def _onchange_kardex(self):
    #     if self.kardex:
    #         domain = [('product_id.kardex', '=', True)]
    #     else:
    #         domain = []
    #     # include only products with kardex=True if picking instance has Kardex=True
    #     _logger.info('onchange called, kardex: %s' % (self.kardex))
    #     return {'domain': {'move_ids': domain}}

    @api.model
    def create(self, vals):
        # Ensure that the product being added has kardex=True if picking has kardex=True
        picking_id = vals.get('picking_id')
        product_id = vals.get('product_id')

        if picking_id and product_id:
            # Retrieve the stock.picking record, see browse docs of odoo
            picking = self.env['stock.picking'].browse(picking_id)
            # Retirve the product
            product = self.env['product.product'].browse(vals.get('product_id'))
            if picking.kardex and not product.kardex:
                raise UserError('You can only add Kardex products.')
        return super(StockMove, self).create(vals)
