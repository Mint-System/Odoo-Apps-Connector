from odoo import fields, models
from odoo.exceptions import UserError


class StockLotDeleteWizard(models.TransientModel):
    _name = "stock.lot.delete.wizard"
    _description = "Delete All Lots/SN with Confirmation"

    confirm = fields.Boolean(string="This action deletes all stock lots, ok?", required=True)

    def action_confirm_delete(self):
        if not self.confirm:
            raise UserError("You must confirm the deletion.")

        # This will delete all stock.lot records
        lots = self.env["stock.lot"].search([])

        lots.sudo().unlink()
