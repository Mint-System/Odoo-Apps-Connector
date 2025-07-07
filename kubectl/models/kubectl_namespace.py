import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class KubectlNamespace(models.Model):
    _name = "kubectl.namespace"
    _description = "Kubectl Namespace"

    name = fields.Char(required=True)
    display_name = fields.Char(compute="_compute_display_name")
    cluster_id = fields.Many2one("kubectl.cluster", required=True)

    def _compute_display_name(self):
        for rec in self:
            rec.display_name = f"{rec.name} ({rec.cluster_id.name})"
