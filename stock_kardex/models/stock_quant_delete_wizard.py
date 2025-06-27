from odoo import fields, models
from odoo.exceptions import UserError

from .config import INCOMING_WAREHOUSE


class StockQuantDeleteWizard(models.TransientModel):
    _name = "stock.quant.delete.wizard"
    _description = "Delete All Stock Quants with Confirmation"

    confirm = fields.Boolean(string="This action deletes all stock quants, ok?", required=True)
    reservation_to_zero = fields.Boolean(string="Set reservations to zero?", default=False)
    set_in_to_zero = fields.Boolean(string="Set IN quantity to zero?", default=False)

    def action_confirm_delete(self):
        if not self.confirm:
            raise UserError("You must confirm the deletion.")

        # This will delete all stock.quant records
        quants = self.env["stock.quant"].search([])

        if not self.set_in_to_zero:
            incoming_location = self.env["stock.location"].search([("name", "=", INCOMING_WAREHOUSE)], limit=1)
            quants = quants.filtered(lambda quant: quant.location_id == incoming_location.id)

        for quant in quants:
            quant.sudo().reserved_quantity = 0
            if self.reservation_to_zero:
                quant.sudo().quantity = 0  # Optional

        quants.sudo().unlink()
