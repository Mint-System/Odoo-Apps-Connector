import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class GitForge(models.Model):
    _name = "git.forge"
    _description = "Git Forge"

    name = fields.Char(required=True)
    hostname = fields.Char(required=True)
    http_url = fields.Char(
        string="HTTP Url", compute="_compute_http_url", readonly=True
    )
    local_path = fields.Char(compute="_compute_local_path")

    def _compute_http_url(self):
        for rec in self:
            rec.http_url = f"https://{rec.hostname}"

    def _compute_local_path(self):
        for rec in self:
            rec.local_path = f"/tmp/{rec.hostname}"
