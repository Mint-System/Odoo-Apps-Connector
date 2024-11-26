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

                # To run the git command with the private key, these commands need to be run:
                # Load ssh agent env vars: eval "$(ssh-agent -s)"
                # Add key to ssh agent: ssh-add /tmp/ssh_private_key_2
                # Don't check host key: export GIT_SSH_COMMAND="ssh -o StrictHostKeyChecking=no"

                output = check_output(["ssh-agent", "-s"], text=True)
                for line in output.splitlines():
                    if "=" in line:
                        key, value = line.split(";")[0].split("=")
                        os.environ[key] = value

                ssh_add_command = [
                    "ssh-add",
                    self.ssh_private_key_filename,
                ]
                output = check_output(ssh_add_command, stderr=STDOUT, timeout=5)

                os.environ["GIT_SSH_COMMAND"] = "ssh -o StrictHostKeyChecking=no"
                output += check_output(git_command, stderr=STDOUT, timeout=5)
                return output

            except Exception as e:
                return e.output if e.output else e
            finally:
                os.remove(self.ssh_private_key_filename)

        return "Missing SSH private key."
