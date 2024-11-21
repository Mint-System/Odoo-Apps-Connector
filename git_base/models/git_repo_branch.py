import logging

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


class GitRepoBranch(models.Model):
    _name = "git.repo.branch"
    _description = "Git Repo Branch"

    name = fields.Char(required=True)
    sequence = field.Int()
    repo_id = fields.Many2one("git.repo", required=True)
    default = fields.Boolean(default=False)