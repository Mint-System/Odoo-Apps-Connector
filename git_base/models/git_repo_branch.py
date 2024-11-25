import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class GitRepoBranch(models.Model):
    _name = "git.repo.branch"
    _description = "Git Repo Branch"

    name = fields.Char(required=True)
    sequence = fields.Integer()
    is_active = fields.Boolean("Active", compute="_compute_is_active")
    repo_id = fields.Many2one("git.repo", required=True)
    upstream = fields.Char()

    _sql_constraints = [
        ("name_unique", "unique(repo_id, name)", "Branch name must be unique.")
    ]

    def _compute_is_active(self):
        for rec in self:
            rec.is_active = rec == self.repo_id.active_branch_id

    def action_switch_branch(self):
        self.ensure_one()
        self.repo_id.cmd_switch(self.name)

    def unlink(self):
        for rec in self:
            rec.repo_id.cmd_delete_branch(rec.name)
        return super().unlink()
