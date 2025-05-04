from odoo import fields, models


class HelmChartInstall(models.TransientModel):
    _name = "helm.chart.install"
    _description = "Helm Chart Install"

    name = fields.Char(string="Release Name", required=True)
    chart_id = fields.Many2one("helm.chart", string="Chart", required=True)
    context_id = fields.Char(string="kubectl.context", required=True)
    partner_id = fields.Many2one("res.partner", string="Customer", required=True)

    def action_confirm(self):
        """
        Create a kubectl.release record and open it.
        """
        for wizard in self:
            # Create the release record
            release = self.env["kubectl.release"].create(
                {
                    "name": wizard.name,
                    "chart_id": wizard.chart_id.id,
                    "context_id": wizard.context_id.id,
                    "partner_id": wizard.partner_id.id,
                }
            )

            # Return an action to open the newly created release
            return {
                "name": "Release",
                "type": "ir.actions.act_window",
                "res_model": "kubectl.release",
                "res_id": release.id,
                "view_mode": "form",
                "target": "current",
            }
