import logging

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


class HelmRepo(models.Model):
    _name = "helm.repo"
    _description = "Helm Repo"

    name = fields.Char()
    url = fields.Char()
    state = fields.Selection(
        selection=[("draft", "Draft"), ("active", "Active")],
        default="draft",
    )

    def add_repo(self):
        return