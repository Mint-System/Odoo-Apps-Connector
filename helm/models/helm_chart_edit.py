import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class HelmChartEdit(models.Model):
    _name = "helm.chart.edit"
    _description = "Helm Chart Edit"

    chart_id = fields.Many2one("helm.chart")
    path = fields.Char()
    code = fields.Char(help="Use Python expressions to return the value.")
    field_id = fields.Many2one(
        "ir.model.fields", domain=[("model", "=", "helm.release")], help="Optionally write value to release field."
    )
