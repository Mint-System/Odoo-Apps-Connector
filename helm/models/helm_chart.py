import logging
import subprocess

from odoo import fields, models

_logger = logging.getLogger(__name__)


class HelmChart(models.Model):
    _name = "helm.chart"
    _description = "Helm Chart"

    name = fields.Char()
    repo_id = fields.Many2one("helm.repo")
    values = fields.Text(compute="_compute_values")
    edit_ids = fields.One2many("helm.chart.edit", "chart_id")
    product_ids = fields.Many2many("product.product")
    state = fields.Selection(related="repo_id.state")

    def _compute_values(self):
        for chart in self:
            result = subprocess.run(
                [
                    "helm",
                    "show",
                    "values",
                    f"{self.repo_id.name}/{self.name}",
                ],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            chart.values = result.stdout

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
