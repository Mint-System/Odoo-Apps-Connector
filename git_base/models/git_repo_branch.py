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
    active_branch = fields.Boolean(compute="_compute_active_branch")

    _sql_constraints = [
        ("name_unique", "unique(repo_id, name)", "Branch name must be unique.")
    ]

    def _compute_active_branch(self):
        for rec in self:
            rec.active_branch = True

    def action_fetch_branch(self):
        self.ensure_one()
        return

    def action_switch_branch(self):
        self.ensure_one()
        return
