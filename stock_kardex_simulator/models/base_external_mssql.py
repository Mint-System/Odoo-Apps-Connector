from odoo import fields, models


class BaseExternalMssql(models.Model):
    _inherit = "base.external.mssql"

    allow_simulation = fields.Boolean(
        string="Allow Kardex Simulation",
        help="Only tick this on a test interface database that no real Kardex reads. "
        "The simulator writes fake Kardex answers into it.",
    )

    def _get_allowed_for_simulation(self):
        return self.allow_simulation and self.priority
