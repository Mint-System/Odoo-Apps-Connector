from odoo import api, fields, models
from .kardex_transfer_mixin import KardexTransferMixin

    

class StockMoveLine(models.Model):
    _inherit = ["stock.move.line", "base.kardex.mixin", "kardex.transfer.mixin"]
    _description = "Stock Move Line"

    has_kardex_location = fields.Boolean(
        string="Is Kardex Location", compute="_compute_has_kardex_location", store=False
    )
    kardex_sync = fields.Boolean(string="Mit Kardex synchronisiert", default=False)

    kardex_id = fields.Integer()
    kardex_done = fields.Boolean(string="in Kardex bekannt", default=False)
    kardex_row_create_time = fields.Char(string="Kardex Row_Create_Time")
    kardex_row_update_time = fields.Char(string="Kardex Row_Update_Time")
    kardex_status = fields.Selection(
        selection=[("0", "Ready"), ("1", "Pending"), ("2", "Success"), ("3", "Error")],
        default="0",
        string="Kardex STATUS",
    )
    kardex_running_id = fields.Char(string="Picking BzId")

    kardex_journal_status = fields.Char(string="Komplett")


    # location_dest_id = fields.Many2one('stock.location', 'To', domain="[('usage', '!=', 'view')]", check_company=True, required=True, compute="_compute_location_dest_id", store=True, readonly=False, precompute=True)

    # @api.depends('move_id', 'move_id.location_id', 'move_id.location_dest_id', 'move_id.product_id.last_location_id')
    # def _compute_location_dest_id(self):
    #     for line in self:
    #         if not line.location_dest_id and line.move_id.product_id.last_location_id:
    #             line.location_dest_id = line.move_id.product_id.last_location_id

    # @api.depends('location_id', 'product_id')
    # def _compute_last_location_id(self):
    #     for record in self:
    #         record.last_location_id = record.location_id
    #         if record.product_id:
    #             last_move = self.env['stock.move'].search([
    #                 ('product_id', '=', product_id.id),
    #                 ('location_dest_id.usage', '=', 'internal'),  # Only internal locations
    #                 ('state', '=', 'done')  # Only completed moves
    #             ], order='date desc', limit=1)

    #             if last_move:
    #                 record.last_location_id = last_move.location_dest_id

    @api.depends("location_id")
    @api.onchange("location_id")
    def _compute_has_kardex_location(self):
        kardex_destination = self.env["stock.location"].search([("name", "=", KARDEX_DESTINATION)], limit=1)
        kardex_location = self.env["stock.location"].search([("name", "=", KARDEX_WAREHOUSE)], limit=1)
        # import pdb; pdb.set_trace()
        for record in self:
            record.has_kardex_location = (
                record.location_dest_id.id == kardex_destination.id or record.location_id.id == kardex_location.id
            )

            

    @api.model_create_multi
    def create(self, vals_list):
        res = super().create(vals_list)
        res.post(lambda rec: rec.send_to_kardex())
        return res

        # _logger.warning("################ STOCK MOVE LINE CREATE ################")
        # _logger.info("### vals_list in stock move line create %s " % (vals_list,))
        # for vals in vals_list:
        #     move_id = vals.get("move_id")
        #     move_obj = self.env["stock.move"].browse(move_id)
        #     picking_id = vals.get("picking_id")
        #     picking_obj = self.env["stock.picking"].browse(picking_id)
        #     location_id = vals.get("location_id")
        #     location_obj = self.env["stock.location"].browse(location_id)
        #     location_dest_id = vals.get("location_dest_id")
        #     location_dest_obj = self.env["stock.location"].browse(location_dest_id)
        #     _logger.warning("### move: %s " % (move_obj.name,))
        #     _logger.warning("### picking: %s " % (picking_obj.name,))
        #     _logger.warning("### picking type: %s " % (picking_obj._check_picking_type()))
        #     _logger.warning("### kardex done: %s " % (picking_obj.kardex_done))
        #     _logger.warning("### location_id: %s " % (location_obj.name,))
        #     _logger.warning("### location_dest_id: %s " % (location_dest_obj.name,))
           

        #     if picking_obj._check_picking_type() == "postproduction" and not picking_obj.kardex_done:
                
        #         if picking_obj._check_if_destination_is_kardex(location_dest_obj):
        #             _logger.warning("### send to kardex %s " % (picking_obj.name,))
        #             picking_obj.kardex_done = True
        #             picking_obj.send_to_kardex(picking_obj.origin)

        #     if picking_obj._check_picking_type() == "sale" and not picking_obj.kardex_done:
                
        #         if picking_obj._check_if_location_is_kardex(location_obj):
        #             _logger.warning("### send to kardex %s " % (picking_obj.name,))
        #             picking_obj.kardex_done = True
        #             picking_obj.send_to_kardex(picking_obj.origin)

            
        # _logger.warning("################ END OF STOCK MOVE LINE CREATE ################")
        # return res
    
