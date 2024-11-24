from odoo.tests.common import TransactionCase


class TestGitRepo(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.forge_id = cls.env["git.forge"].create(
            {
                "name": "GitHub",
                "hostname": "github.com",
            }
        )
        cls.account_id = cls.env["git.account"].create(
            {
                "name": "Mint System",
                "http_url": "https://github.com/Mint-System",
                "forge_id": cls.forge_id.id,
            }
        )
        cls.repo_id = cls.env["git.repo"].create(
            {
                "name": "Project-MCC",
                "account_id": cls.account_id.id,
            }
        )

    def test_init(self):
        self.repo_id.cmd_init()
        self.assertEqual(self.repo_id.state, "initialized")

    # def test_input_file_commit(self):
