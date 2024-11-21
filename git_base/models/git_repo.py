import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class GitRepo(models.Model):
    _name = "git.repo"
    _description = "Git Repo"

    name = fields.Char(required=True)
    http_url = fields.Char(
        string="HTTP Url", compute="_compute_http_url", readonly=True
    )
    ssh_url = fields.Char(string="SSH Url", compute="_compute_ssh_url", readonly=True)
    push_url = fields.Char(string="Push Url", default="")
    pull_url = fields.Char(string="Pull Url", default="")

    account_id = fields.Many2one("git.account", required=True)
    forge_id = fields.Many2one("git.forge", related="account_id.forge_id")

    def _compute_http_url(self):
        for rec in self:
            rec.http_url = f"{rec.account_id.http_url}/{rec.name}"

    def _compute_ssh_url(self):
        for rec in self:
            rec.ss_url = f"git@{rec.forge_id.hostname}:{rec.name}/{rec.name}.git"
