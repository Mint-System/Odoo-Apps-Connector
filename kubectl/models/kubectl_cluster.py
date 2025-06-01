import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class KubectlCluster(models.Model):
    _name = "kubectl.cluster"
    _description = "Kubectl Cluster"

    name = fields.Char()
    display_name = fields.Char(compute="_compute_display_name")
    server = fields.Char()
    code = fields.Char()
    domain = fields.Char()
    provider_id = fields.Many2one("res.partner", domain="[('is_provider','=', True)]")

    def _compute_display_name(self):
        for rec in self:
            rec.display_name = f"{rec.name} ({rec.provider_id.name})"
