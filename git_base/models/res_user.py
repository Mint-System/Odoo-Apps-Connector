import os
import tempfile

from odoo import fields, models


class ResUsers(models.Model):
    _inherit = "res.users"

    ssh_private_key_password = fields.Char("SSH Private Key Password")
    ssh_private_key = fields.Text("SSH Private Key")

    def load_ssh_key(self):
        self.ensure_one()

        # Write the private key to a temporary file
        self.private_key_file = tempfile.NamedTemporaryFile(delete=False)
        self.private_key_file.write(self.ssh_private_key.encode())
        self.private_key_file.close()

        # Set up the SSH command with the private key
        ssh_cmd = f"ssh -i {self.private_key_file.name}"
        if self.ssh_private_key_password:
            ssh_cmd += ' -o "IdentityAgent none" -o "KbdInteractiveAuthentication no" -o "PasswordAuthentication no" -o "IdentitiesOnly yes" -o "BatchMode yes"'

        # Set the GIT_SSH environment variable to use the custom SSH command
        os.environ["GIT_SSH_COMMAND"] = ssh_cmd

    def clear_ssh_key(self):
        self.ensure_one()

        # Clean up the temporary private key file
        if self.private_key_file:
            os.remove(self.private_key_file.name)
            del os.environ["GIT_SSH_COMMAND"]
            del self.private_key_file
