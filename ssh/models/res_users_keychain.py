import base64
import logging
import os
from subprocess import STDOUT, CalledProcessError, check_output, run

from odoo import api, models

_logger = logging.getLogger(__name__)


class ResUsersKeychain(models.AbstractModel):
    _name = "res.users.keychain"
    _description = "Keychain"

    def _get_keychain(self):
        """
        Return keychain in order: deploy > user > personal > company
        """
        if hasattr(self, "ssh_private_key_file") and self.ssh_private_key_file:
            return self
        elif hasattr(self, "user_id") and self.user_id and self.user_id.ssh_private_key_file:
            return self.user_id
        elif self.env.user.ssh_private_key_file:
            return self.env.user
        elif self.env.company.ssh_private_key_file:
            return self.env.company
        else:
            return False

    @api.model
    def generate_ssh_keys(self, comment, output_keyfile, new_passphrase=""):
        ssh_keygen_command = [
            "ssh-keygen",
            "-t",
            "ed25519",
            "-C",
            comment,
            "-f",
            output_keyfile,
            "-N",
            new_passphrase,
        ]
        run(ssh_keygen_command)

        # Read public key
        ssh_public_key = ""
        with open(f"{output_keyfile}.pub") as file:
            ssh_public_key = file.read()

        # Read private key
        ssh_private_key_file = ""
        with open(f"{output_keyfile}", "rb") as file:
            ssh_private_key_file = base64.b64encode(file.read())

        os.remove(f"{output_keyfile}.pub")
        os.remove(f"{output_keyfile}")

        return ssh_public_key, ssh_private_key_file

    def run_ssh_command(self, command, timeout=10):
        """
        Context manager to set up the SSH environment.
        """

        keychain = self._get_keychain()
        if keychain and keychain.ssh_private_key_file:
            try:
                with open(keychain.ssh_private_key_filename, "wb") as file:
                    file.write(base64.b64decode(keychain.ssh_private_key_file))
                os.chmod(keychain.ssh_private_key_filename, 0o600)

                # To run the git command with the private key, these commands need to be run:
                # Load ssh agent env vars: eval "$(ssh-agent -s)"
                # Add key to ssh agent: ssh-add /tmp/user_private_key_$ID
                # Don't check host key and pass key file: GIT_SSH_COMMAND="ssh -o StrictHostKeyChecking=no -i /tmp/user_private_key_$ID"

                output = check_output(["ssh-agent", "-s"], text=True)
                for line in output.splitlines():
                    if "=" in line:
                        key, value = line.split(";")[0].split("=")
                        os.environ[key] = value

                ssh_add_command = [
                    "ssh-add",
                    keychain.ssh_private_key_filename,
                ]
                # _logger.warning(" ".join(ssh_add_command))
                output = check_output(ssh_add_command, stderr=STDOUT, text=True)

                os.environ["GIT_SSH_COMMAND"] = (
                    f"ssh -o StrictHostKeyChecking=no -i {keychain.ssh_private_key_filename}"
                )
                # _logger.warning(" ".join(command))
                output += check_output(command, stderr=STDOUT, timeout=timeout, text=True)
                return output
            except CalledProcessError as e:
                raise Exception(e.output)
            finally:
                os.remove(keychain.ssh_private_key_filename)
        return "Missing SSH private key."
