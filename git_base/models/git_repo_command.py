import logging

from odoo import _, api, fields, models
from odoo.osv import expression

_logger = logging.getLogger(__name__)


class GitRepoCommand(models.Model):
    _name = "git.repo.cmd"
    _description = "Git Repo Command"

    sequence = fields.Integer()
    name = fields.Char(required=True)
    code = fields.Char(required=True)
    command = fields.Char(required=True)
    help = fields.Char(required=True)
    states = fields.Char(required=True)
    has_input = fields.Boolean(default=False)
    clear_input = fields.Boolean(default=False)
    tracking = fields.Boolean(default=False)
    next_command_id = fields.Many2one("git.repo.cmd")

    def name_get(self):
        res = []
        for rec in self:
            res.append((rec.id, _("%s > %s") % (rec.name, rec.command)))
        return res

    @api.model
    def _name_search(
        self, name, args=None, operator="ilike", limit=100, name_get_uid=None
    ):
        args = args or []
        domain = []
        if name:
            domain = ["|", ("name", operator, name), ("command", operator, name)]
        return self._search(
            expression.AND([domain, args]), limit=limit, access_rights_uid=name_get_uid
        )
