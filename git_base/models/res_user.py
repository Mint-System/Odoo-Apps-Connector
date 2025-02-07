import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class ResUsers(models.Model):
    _inherit = "res.users"

    ssh_public_key = fields.Char("SSH Public Key")
    ssh_private_key_file = fields.Binary("SSH Private Key")
    ssh_private_key_filename = fields.Char(
        "SSH Private Key Filename", compute="_compute_ssh_private_key_filename"
    )
    ssh_private_key_password = fields.Char("SSH Private Key Password")

    @property
    def SELF_READABLE_FIELDS(self):
        return super().SELF_READABLE_FIELDS + [
            "ssh_public_key",
            "ssh_private_key_file",
            "ssh_private_key_filename",
            "ssh_private_key_password",
        ]

    def _compute_ssh_private_key_filename(self):
        for user in self:
            user.ssh_private_key_filename = f"/tmp/user_private_key_{self.id}"
