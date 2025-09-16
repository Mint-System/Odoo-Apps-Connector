import logging
import subprocess

from odoo import fields, models

_logger = logging.getLogger(__name__)


class HelmChart(models.Model):
    _name = "helm.chart"
    _description = "Helm Chart"

    name = fields.Char(required=True)
    repo_id = fields.Many2one("helm.repo", required=True)
    values = fields.Text(compute="_compute_values", string="Chart values.yaml")
    value_ids = fields.One2many("helm.chart.value", "chart_id", string="Custom values.yaml")
    product_ids = fields.One2many("product.product", "chart_id")
    state = fields.Selection(related="repo_id.state")

    def _compute_values(self):
        for chart in self:
            if chart.state == "added":
                result = subprocess.run(
                    [
                        "helm",
                        "show",
                        "values",
                        f"{chart.repo_id.name}/{chart.name}",
                    ],
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                chart.values = result.stdout
            else:
                chart.values = ""

    def create_release(self, namespace_id, partner_id):
        self.ensure_one()
        return self.env["helm.release"].create(
            {
                "name": self.name,
                "chart_id": self.id,
                "context_id": namespace_id.cluster_id.cluster_ids[0].id,
                "namespace_id": namespace_id.id,
                "partner_id": partner_id.id,
            }
        )

    def action_release(self):
        """
        Opens the release wizard when the Release button is clicked.
        """
        return {
            "name": "Create Release",
            "type": "ir.actions.act_window",
            "res_model": "helm.chart.install",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_chart_id": self.id,
            },
        }
