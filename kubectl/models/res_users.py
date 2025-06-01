import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class ResUsers(models.Model):
    _inherit = "res.users"

    kubectl_context_ids = fields.Many2many("kubectl.context")
