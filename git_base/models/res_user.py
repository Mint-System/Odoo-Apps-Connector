import logging
import os
import tempfile
from contextlib import contextmanager
from subprocess import STDOUT, check_output

from odoo import fields, models

_logger = logging.getLogger(__name__)


class ResUsers(models.Model):
    _inherit = "res.users"

    ssh_public_key = fields.Char("SSH Public Key")
    ssh_private_key = fields.Text("SSH Private Key")
    ssh_private_key_password = fields.Char("SSH Private Key Password")

    @contextmanager
    def ssh_env(self):
        """Context manager to set up the SSH environment for Git operations."""

        if self.ssh_private_key:
            private_key_file = tempfile.NamedTemporaryFile(delete=False)
            try:
                private_key_file.write(self.ssh_private_key.encode("utf-8"))
                private_key_file.close()

                # Set the SSH environment variables
                env = os.environ.copy()
                env["GIT_SSH_COMMAND"] = f"ssh -i {private_key_file.name}"

                if self.ssh_private_key_password:
                    env["GIT_ASKPASS"] = "echo"
                    env["GIT_ASKPASS_STDIN"] = self.ssh_private_key_password

                # Yield the environment to the calling function
                yield env
            finally:
                os.remove(private_key_file.name)
        else:
            env = os.environ.copy()
            env["GIT_SSH_COMMAND"] = ""
            env["GIT_ASKPASS"] = ""
            env["GIT_ASKPASS_STDIN"] = ""
            yield env

    def ssh_test(self, hostname):
        if self.ssh_private_key:
            with tempfile.NamedTemporaryFile(delete=False) as private_key_file:
                try:
                    # Write the private key to the temporary file
                    private_key_file.write(self.ssh_private_key.encode("utf-8"))
                    private_key_file.close()

                    output = check_output(
                        [
                            "ssh",
                            "-i",
                            private_key_file.name,
                            "-o",
                            "StrictHostKeyChecking=no",
                            "-T",
                            f"git@{hostname}",
                        ],
                        stderr=STDOUT,
                    )
                    return output.decode("utf-8")
                except Exception as e:
                    return str(e)
                finally:
                    os.remove(private_key_file.name)
        else:
            return "Missing SSH private key."
