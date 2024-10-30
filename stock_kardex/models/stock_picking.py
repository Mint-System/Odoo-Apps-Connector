import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

PICKING_DATE_HANDLING = 'send' # or 'create'


class StockPicking(models.Model):
    _name = 'stock.picking'
    _inherit = ['stock.picking', 'base.kardex.mixin']
    _description = 'Stock Kardex Picking'

    kardex = fields.Boolean(string='Kardex', default=False)
    kardex_id = fields.Integer(string='Kardex Id')
    kardex_done = fields.Boolean(string="in Kardex bekannt", default=False)
    kardex_row_create_time = fields.Char(string="Kardex Row_Create_Time")
    kardex_row_update_time = fields.Char(string="Kardex Row_Update_Time")
    kardex_status = fields.Selection(selection=[('0', 'Ready'), ('1', 'Pending'), ('2', 'Success'), ('3', 'Error')], default='0', string="Kardex STATUS")

    def send_to_kardex(self):
        
        for picking in self:
            picking_vals = picking.read()[0]
            # get moves belonging to this picking
            moves = self.env['stock.move'].search([('picking_id', '=', picking.id)])
            if not moves:
                raise ValidationError('No moves found for this picking')
            check_moves_counter = 0
            check_moves_list = []
            for move in moves:
                print(f"Product: {move.product_id.name}")
                if not move.product_id.kardex_done:
                    check_moves_counter += 1
                    check_moves_list.append(move.product_id.name)

            if check_moves_counter > 0:
                raise ValidationError(f"These Products are unknown in Kardex: {', '.join(check_moves_list)}. Please transfer Products to Kardex.")
                return

            # create external object for every picking record 
            for move in moves:
                table = 'PPG_Auftraege'
                # add ID of products zo picking vals
                picking_vals['kardex_product_id'] = move.product_id.kardex_id
                #create_time, update_time = self._get_dates(move, PICKING_DATE_HANDLING)
                #picking_vals['kardex_row_create_time'] = create_time
                #picking_vals['kardex_row_update_time'] = update_time
                picking_vals['kardex_status'] = '1'
                picking_vals['kardex_unit'] = move.product_id.uom_id.name
                picking_vals['kardex_quantity'] = move.quantity
                new_id, create_time, update_time = self._create_external_object(picking_vals, table)
                # new_id = self._create_external_object(picking_vals, table)
                
                _logger.info('new_id: %s' % (new_id,))

                
                done_move = {
                    'kardex_done': True,
                    'kardex_id': new_id,
                    'kardex_status': '1',
                    'kardex_row_create_time': create_time,
                    'kardex_row_update_time': update_time
                    }
                move.write(done_move)
                message = 'Kardex Picking was sent to Kardex.'

            done_picking = {
                    'kardex_done': True,
                    'kardex_row_create_time': create_time,
                    'kardex_row_update_time': update_time
                }
            picking.write(done_picking)    
            return self._create_notification(message)

    @api.model
    def write(self, vals):
        res = super(StockPicking, self).write(vals)
        
        # Check if the 'kardex_done' field is being updated
        if 'kardex_done' in vals:
            for picking in self:
                # Update the 'kardex' field in related stock.move records
                picking.move_ids.write({'kardex_done': vals['kardex_done']})

        return res
            

    

class StockMove(models.Model):
    _inherit = ['stock.move']
    products_domain = fields.Binary(string="products domain", help="Dynamic domain used for the products that can be chosen on a move line", compute="_compute_products_domain")
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        domain="[('kardex', '=', parent.kardex)]",
    ) # this adds domain to existing domain!
    kardex_id = fields.Integer(string='Kardex Id')
    kardex_done = fields.Boolean(string="in Kardex bekannt", default=False)
    kardex_row_create_time = fields.Char(string="Kardex Row_Create_Time")
    kardex_row_update_time = fields.Char(string="Kardex Row_Update_Time")
    kardex_status = fields.Selection(selection=[('0', 'Ready'), ('1', 'Pending'), ('2', 'Success'), ('3', 'Error')], default='0', string="Kardex STATUS")



    @api.depends('picking_id.kardex')
    def _compute_products_domain(self):
        # if picking is kardex than product must be kardex too
        # could also be done by onchange but dynamic domain setting by onchange method seems to deprecated in odoo 17
        # field products_domain must be included in view
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
