from odoo.tests.common import TransactionCase


class TestGitRepo(TransactionCase):
    @classmethod
    def setUpClass(self):
        super().setUpClass()

        self.forge_id = self.env["git.forge"].create(
            {
                "name": "GitHub",
                "hostname": "github.com",
            }
        )
        self.account_id = self.env["git.account"].create(
            {
                "name": "Mint System",
                "http_url": "https://github.com/Mint-System",
                "forge_id": self.forge_id.id,
            }
        )
        self.repo_id = self.env["git.repo"].create(
            {
                "name": "Project-MCC",
                "account_id": self.account_id.id,
            }
        )

    def test_init(self):
        self.repo_id.cmd_init()
        self.assertEqual(self.repo_id.state, "initialized")

    # def test_input_file_commit(self):
