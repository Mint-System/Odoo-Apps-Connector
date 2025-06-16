from odoo import models, fields, api
from odoo.exceptions import UserError

class StockQuantDeleteWizard(models.TransientModel):
    _name = 'stock.quant.delete.wizard'
    _description = 'Delete All Stock Quants with Confirmation'

    confirm = fields.Boolean(string="This action deletes all stock quants, ok?", required=True)

    def action_confirm_delete(self):
        if not self.confirm:
            raise UserError("You must confirm the deletion.")

        # This will delete all stock.quant records

        quants = self.env['stock.quant'].search([])
        for quant in quants:
            quant.sudo().reserved_quantity = 0
            quant.sudo().quantity = 0  # Optional
            
        quants.sudo().unlink()
