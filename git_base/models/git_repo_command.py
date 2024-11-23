import logging

from odoo import _, fields, models

_logger = logging.getLogger(__name__)


class GitRepoCommand(models.Model):
    _name = "git.repo.cmd"
    _description = "Git Repo Command"

    name = fields.Char(required=True)
    command = fields.Char(required=True)
    states = fields.Char(required=True)
    show_input = fields.Boolean(default=False)

    def name_get(self):
        res = []
        for rec in self:
            res.append((rec.id, _("%s / %s") % (rec.name, rec.command)))
        return res
