import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class GitAccount(models.Model):
    _name = "git.account"
    _description = "Git Account"

    name = fields.Char(required=True)
    http_url = fields.Char(string="HTTP Url", compute="_compute_http_url")
    forge_id = fields.Many2one("git.forge", required=True)
    local_path = fields.Char(compute="_compute_local_path")

    def _compute_http_url(self):
        for rec in self:
            rec.http_url = f"{rec.forge_id.http_url}/{rec.name}"

    def _compute_local_path(self):
        for rec in self:
            rec.local_path = f"{rec.forge_id.local_path}/{rec.name}"
