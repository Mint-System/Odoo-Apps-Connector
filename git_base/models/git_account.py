import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class GitAccount(models.Model):
    _name = "git.account"
    _description = "Git Account"

    name = fields.Char(required=True)
    forge_id = fields.Char("git.forge", required=True)
    http_url = fields.Char(
        string="HTTP Url", compute="_compute_http_url", required=True
    )

    def _compute_http_url(self):
        for rec in self:
            rec.http_url = f"{rec.forge_id.http_url}/{recc.name}"
