import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    module_git_base = fields.Boolean("Integrate with Git")
    ssh_public_key = fields.Char(
        "SSH Public Key", config_parameter="git.ssh_public_key"
    )
    ssh_private_key = fields.Char(
        "SSH Private Key", config_parameter="git.ssh_private_key"
    )
