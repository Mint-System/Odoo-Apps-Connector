import os
import tempfile
from contextlib import contextmanager

from odoo import fields, models


class ResUsers(models.Model):
    _inherit = "res.users"

    ssh_public_key = fields.Char("SSH Public Key")
    ssh_private_key = fields.Text("SSH Private Key")
    ssh_private_key_password = fields.Char("SSH Private Key Password")

    @contextmanager
    def ssh_env(self):
        """Context manager to set up the SSH environment for Git operations."""

        private_key_file = tempfile.NamedTemporaryFile(delete=False)
        try:
            private_key_file.write(self.ssh_private_key.encode("utf-8"))
            private_key_file.close()

            env = os.environ.copy()
            env[
                "GIT_SSH_COMMAND"
            ] = f"ssh -i {private_key_file.name} -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no"

            if self.ssh_private_key_password:
                env[
                    "GIT_SSH_COMMAND"
                ] += " -o PasswordAuthentication=yes -o IdentitiesOnly=yes"
                env["SSH_ASKPASS"] = "/bin/echo"
                env["SSH_PASS"] = self.ssh_private_key_password

            # Yield the environment to the calling function
            yield env
        finally:
            os.remove(private_key_file.name)
