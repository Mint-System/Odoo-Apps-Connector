# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class HelmChartValue(models.Model):
    _name = "helm.chart.value"
    _description = "Helm Chart Value"

    chart_id = fields.Many2one("helm.chart")
    path = fields.Selection(selection=[("ingress.host", "ingess.host")])
    code = fields.Char()
