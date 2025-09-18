import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class HelmChartValue(models.Model):
    _name = "helm.chart.value"
    _description = "Helm Chart Value"

    chart_id = fields.Many2one("helm.chart")
    release_chart_id = fields.Many2one("helm.chart")
    release_id = fields.Many2one("helm.release")
    apply = fields.Char(help="Expression that tells if value should be applied.", required=True, default="True")
    path = fields.Char(help="Path to the nested key of the values.yaml.", required=True)
    value = fields.Char(help="Python code to define the value.")
    option_id = fields.Many2one(
        "helm.chart.value.option", domain="[('value_id', '=', id)]", help="Select value from options."
    )
    field_id = fields.Many2one(
        "ir.model.fields", domain=[("model", "=", "helm.release")], help="Optionally write value to this release field."
    )

    def _compute_display_name(self):
        for rec in self:
            rec.display_name = rec.path


class HelmChartValueOption(models.Model):
    _name = "helm.chart.value.option"
    _description = "Helm Chart Value Option"

    value_id = fields.Many2one("helm.chart.value", required=True)
    value = fields.Char(required=True)

    _sql_constraints = [
        (
            "unique_value_by_value_id",
            "UNIQUE(value, value_id)",
            "Value option must be unique per value.",
        ),
    ]

    def _compute_display_name(self):
        for rec in self:
            rec.display_name = rec.value
