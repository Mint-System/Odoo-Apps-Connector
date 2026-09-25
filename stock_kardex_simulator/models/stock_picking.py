from odoo import _, models, fields


class StockPicking(models.Model):
    _inherit = "stock.picking"

    simulated = fields.Boolean("Simulated", default=False)

    def action_open_kardex_simulator(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Kardex Simulator"),
            "res_model": "kardex.simulator.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_picking_id": self.id},
        }


