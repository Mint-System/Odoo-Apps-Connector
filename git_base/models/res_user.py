import base64
import logging
import os
from subprocess import STDOUT, check_output

from odoo import fields, models

_logger = logging.getLogger(__name__)


class ResUsers(models.Model):
    _inherit = "res.users"

    ssh_private_key_file = fields.Binary("SSH Private Key")
    ssh_private_key_filename = fields.Char(
        "SSH Private Key Filepath", compute="_compute_ssh_private_key_filename"
    )
    ssh_private_key_password = fields.Char("SSH Private Key Password")

    def _compute_ssh_private_key_filename(self):
        for user in self:
            user.ssh_private_key_filename = f"/tmp/ssh_private_key_{self.id}"

    def ssh_command(self, git_command):
        """Context manager to set up the SSH environment for Git operations."""
        self.ensure_one()

        if self.ssh_private_key_file:
            try:
                with open(self.ssh_private_key_filename, "wb") as file:
                    file.write(base64.b64decode(self.ssh_private_key_file))
                os.chmod(self.ssh_private_key_filename, 0o600)

                sshpass_command = []
                if self.ssh_private_key_password:
                    sshpass_command = [
                        f"SSHPASS={self.ssh_private_key_password}",
                        "sshpass",
                        "-e",
                    ]
                command = [
                    "ssh-add",
                    self.ssh_private_key_filename,
                ] + sshpass_command
                # _logger.warning(" ".join(command))
                output = check_output(command, stderr=STDOUT, timeout=5)

                sshpass_command = []
                if self.ssh_private_key_password:
                    sshpass_command = [
                        f"SSHPASS={self.ssh_private_key_password}",
                        "sshpass",
                        "-e",
                    ]
                command = sshpass_command + git_command
                # _logger.warning(" ".join(command))
                output += check_output(git_command, stderr=STDOUT, timeout=5)
                return output

            except Exception as e:
                return e.output
            finally:
                os.remove(self.ssh_private_key_filename)

        return "Missing SSH private key."
