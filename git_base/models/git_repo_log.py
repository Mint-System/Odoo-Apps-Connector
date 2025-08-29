import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class GitRepoLog(models.TransientModel):
    _name = "git.repo.log"
    _description = "Git Repo Log"

    commit = fields.Char()
    author = fields.Char()
    date = fields.Datetime()
    message = fields.Char()
    repo_id = fields.Many2one("git.repo")
