import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class GitRepoBranch(models.Model):
    _name = "git.repo.branch"
    _description = "Git Repo Branch"

    name = fields.Char(required=True)
    sequence = fields.Integer()
    default = fields.Boolean(default=False)
    repo_id = fields.Many2one("git.repo", required=True)
