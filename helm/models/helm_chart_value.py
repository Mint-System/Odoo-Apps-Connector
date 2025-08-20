import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class HelmChartEdit(models.Model):
    _name = "helm.chart.value"
    _description = "Helm Chart Value"

    chart_id = fields.Many2one("helm.chart", required=True)
    apply = fields.Char(help="Python code that defines if value should be applied.", required=True, default="True")
    path = fields.Char(required=True)
    value = fields.Char(help="Python code to define the value.", required=True)
    field_id = fields.Many2one(
        "ir.model.fields", domain=[("model", "=", "helm.release")], help="Optionally write value to release field."
    )
