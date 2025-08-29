import logging

from odoo.tests.common import TransactionCase

_logger = logging.getLogger(__name__)


class ResUsersKeychain(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

    def test_generate_ssh_key(self):
        # Generate ssh keys for current user
        keychain_model = self.env["res.users.keychain"]
        ssh_public_key, ssh_private_key_file = keychain_model.generate_ssh_keys(
            "git@codeberg.org", "test_repo_private_key"
        )
        self.env.user.write(
            {
                "ssh_public_key": ssh_public_key,
                "ssh_private_key_file": ssh_private_key_file,
            }
        )

        # Load keychain and run test command
        keychain = keychain_model._get_keychain()
        with self.assertRaises(Exception) as context:
            output = keychain_model.run_ssh_command(
                [
                    "ssh",
                    "-i",
                    keychain.ssh_private_key_filename,
                    "-o",
                    "StrictHostKeyChecking=no",
                    "-T",
                    "git@codeberg.org",
                ]
            )
        self.assertIn("Permission denied (publickey)", str(context.exception))
