import logging
import os

from odoo.tests.common import TransactionCase
from odoo.tools import file_open

_logger = logging.getLogger(__name__)


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
                "name": "Mint-System",
                "forge_id": cls.forge_id.id,
            }
        )
        cls.repo_id = cls.env["git.repo"].create(
            {
                "name": "Project-MCC",
                "account_id": cls.account_id.id,
            }
        )

    def test_git_repo_commands(self):
        self.repo_id.cmd_remove()
        self.assertEqual(self.repo_id.state, "deleted")

        self.repo_id.cmd_init()
        self.assertEqual(self.repo_id.state, "initialized")

        with open(
            os.path.join(self.repo_id.local_path, "test.txt"), "w"
        ) as target_file:
            with file_open("git_base/tests/test.txt", "r") as source_file:
                target_file.write(source_file.read())

        self.repo_id.cmd_list()
        self.assertTrue("test.txt" in self.repo_id.cmd_output, self.repo_id.cmd_output)

        self.repo_id.cmd_add_all()
        self.repo_id.cmd_status()
        self.assertTrue("new file:   test.txt" in self.repo_id.cmd_output)

        self.repo_id.write({"cmd_input": "Test commit"})
        self.repo_id.cmd_commit()
        self.repo_id.cmd_log()
        self.assertTrue(
            "Test commit" in self.repo_id.cmd_output, self.repo_id.cmd_output
        )

        self.repo_id.cmd_switch("dev")
        self.repo_id.cmd_branch_list()
        self.assertTrue("dev" in self.repo_id.cmd_output)

        self.repo_id.cmd_delete_branch("master")
        self.assertTrue(len(self.repo_id.branch_ids) == 2, self.repo_id.branch_ids)

        self.repo_id.write({"cmd_input": "new_folder"})
        self.repo_id.cmd_mkdir()
        self.repo_id.cmd_list()
        self.assertTrue(
            "new_folder" in self.repo_id.cmd_output, self.repo_id.cmd_output
        )

    def test_git_repo_keys(self):
        author = f"{self.account_id.name}-{self.repo_id.name}@{self.forge_id.hostname}"
        self.repo_id.action_generate_deploy_keys()
        self.assertTrue(
            author in self.repo_id.ssh_public_key, self.repo_id.ssh_public_key
        )
