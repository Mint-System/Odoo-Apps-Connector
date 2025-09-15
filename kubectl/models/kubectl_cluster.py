import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class KubectlCluster(models.Model):
    _name = "kubectl.cluster"
    _description = "Kubectl Cluster"
    _resource = "cluster"

    name = fields.Char(required=True)
    display_name = fields.Char(compute="_compute_display_name")
    server = fields.Char(required=True)
    code = fields.Char(required=True)
    domain = fields.Char(required=True)
    provider_id = fields.Many2one("res.partner", domain="[('is_provider','=', True)]", required=True)
    context_ids = fields.One2many("kubectl.context", "cluster_id")

    def _compute_display_name(self):
        for rec in self:
            rec.display_name = f"{rec.name} ({rec.provider_id.name})"
