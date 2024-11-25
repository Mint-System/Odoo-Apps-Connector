import base64
import logging
import os
from subprocess import STDOUT, check_output

from odoo import fields, models
from odoo.tools import config

_logger = logging.getLogger(__name__)


class ResUsers(models.Model):
    _inherit = "res.users"

    ssh_public_key = fields.Char("SSH Public Key")
    ssh_private_key_file = fields.Binary("SSH Private Key")
    ssh_private_key_filename = fields.Char(
        "SSH Private Key Filepath", compute="_compute_ssh_private_key_filename"
    )
    ssh_private_key_password = fields.Char("SSH Private Key Password")

    def _compute_ssh_private_key_filename(self):
        for user in self:
            user.ssh_private_key_filename = (
                f"{config['data_dir']}/ssh/ssh_private_key_{self.id}"
            )

    def ensure_local_path_exists(self):
        self.ensure_one()
        if not os.path.exists(f"{config['data_dir']}/ssh/"):
            os.makedirs(f"{config['data_dir']}/ssh/")

    def ssh_command(self, git_command):
        """Context manager to set up the SSH environment for Git operations."""

        self.ensure_local_path_exists()
        if self.ssh_private_key_file:
            try:
                with open(self.ssh_private_key_filename, "wb") as file:
                    file.write(base64.b64decode(self.ssh_private_key_file))
                os.chmod(self.ssh_private_key_filename, 0o600)

                command = []
                ssh_add_command = [
                    "ssh-add",
                    self.ssh_private_key_filename,
                ]
                if self.ssh_private_key_password:
                    command = [
                        "sshpass",
                        "-p",
                        self.ssh_private_key_password,
                    ] + ssh_add_command
                _logger.warning([self.ssh_private_key_password, command])
                output = check_output(command, stderr=STDOUT, timeout=5)
                command = []
                if self.ssh_private_key_password:
                    command = [
                        "sshpass",
                        "-p",
                        self.ssh_private_key_password,
                    ] + git_command
                _logger.warning([self.ssh_private_key_password, command])
                output += check_output(command, stderr=STDOUT, timeout=5)
                return output
            except Exception as e:
                return e
            # finally:
            # os.remove(self.ssh_private_key_filename)
        return "Missing SSH private key."
