from odoo import fields, models


class HelmChartInstall(models.TransientModel):
    _name = "helm.chart.install"
    _description = "Helm Chart Install"

    name = fields.Char(string="Release Name", required=True)
    chart_id = fields.Many2one("helm.chart", required=True)
    context_id = fields.Many2one("kubectl.context", required=True)
    create_namespace = fields.Boolean()
    namespace = fields.Char()
    namespace_id = fields.Many2one("kubectl.namespace", required=True)
    partner_id = fields.Many2one("res.partner", string="Customer", required=True)

    def action_confirm(self):
        """
        Create a kubectl.release record and open it.
        """
        for wizard in self:
            release_value_ids = wizard.chart_id.release_value_ids.copy()
            release_id = self.env["helm.release"].create(
                {
                    "name": wizard.name,
                    "chart_id": wizard.chart_id.id,
                    "context_id": wizard.context_id.id,
                    "create_namespace": wizard.create_namespace,
                    "namespace": wizard.namespace,
                    "namespace_id": wizard.namespace_id.id,
                    "partner_id": wizard.partner_id.id,
                    "value_ids": release_value_ids.ids,
                }
            )
            release_value_ids.write({"chart_id": False, "release_id": release_id.id})

            return {
                "name": "Release",
                "type": "ir.actions.act_window",
                "res_model": "helm.release",
                "res_id": release_id.id,
                "view_mode": "form",
                "target": "current",
            }
