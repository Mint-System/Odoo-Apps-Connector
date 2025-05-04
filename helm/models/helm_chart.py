import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class HelmChart(models.Model):
    _name = "helm.chart"
    _description = "Helm Chart"

    name = fields.Char()
    repo_id = fields.Many2one("helm.repo")
    product_ids = fields.Many2many("product.template")

    def action_release(self):
        """
        Opens the release wizard when the Release button is clicked.
        """
        return {
            "name": "Create Release",
            "type": "ir.actions.act_window",
            "res_model": "kubectl.chart.install",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_chart_id": self.id,
            },
        }
