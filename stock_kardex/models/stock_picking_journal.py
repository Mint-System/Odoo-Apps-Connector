from odoo import api, fields, models


class StockPickingJournal(models.Model):
    _name = "stock.picking.journal"
    _description = "Stock Picking Journal"

    journal_id = fields.Integer(required=True)
    kardex_running_id = fields.Integer(string="BzId", required=True)

    _sql_constraints = [("unique_journal", "unique(journal_id)", "The Journal ID must be unique!")]

    @api.model
    def create(self, vals):
        existing = self.search([("journal_id", "=", vals.get("journal_id"))], limit=1)
        if existing:
            # Update existing record with new kardex_running_id
            existing.kardex_running_id = vals.get("kardex_running_id")
            return existing
        return super().create(vals)
