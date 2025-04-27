import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class HelmChart(models.Model):
    _name = "helm.chart"
    _description = "Helm Chart"

    name = fields.Char()
    repo_id = fields.Many2one("helm.repo")

    def install(self):
        return
