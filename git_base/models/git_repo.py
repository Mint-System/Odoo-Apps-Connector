import logging
import subprocess

import git

from odoo import fields, models

_logger = logging.getLogger(__name__)


class GitRepo(models.Model):
    _name = "git.repo"
    _description = "Git Repo"

    name = fields.Char(required=True)
    http_url = fields.Char(
        string="HTTP Url", compute="_compute_http_url", readonly=True
    )
    ssh_url = fields.Char(string="SSH Url", compute="_compute_ssh_url", readonly=True)
    push_url = fields.Char(default="")
    pull_url = fields.Char(default="")
    local_path = fields.Char(compute="_compute_local_path")

    status = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("initialized", "Initialized"),
            ("cloned", "Cloned"),
        ]
    )
    cmd = fields.Selection(
        selection=[
            ("status", "git status"),
            ("log", "git log"),
            ("clean", "git clean -fd"),
            ("add_all", "git add -A"),
            ("unstage", "git restore --staged"),
            ("commit", "git commit -m"),
            ("init", "git init"),
            ("clone", "git clone"),
            ("remove", "rm -rf"),
            ("set_url", "git remote set-url origin"),
        ],
        default="status",
    )
    cmd_input = fields.Text()
    cmd_input_file = fields.Binary()
    cmd_output = fields.Text(readonly=True)

    user_id = fields.Many2one("res.users")
    branch_ids = fields.One2many("git.repo.branch", "repo_id")

    account_id = fields.Many2one("git.account", required=True)
    forge_id = fields.Many2one("git.forge", related="account_id.forge_id")

    def _compute_http_url(self):
        for rec in self:
            rec.http_url = f"{rec.account_id.http_url}/{rec.name}"

    def _compute_ssh_url(self):
        for rec in self:
            rec.ssh_url = f"git@{rec.forge_id.hostname}:{rec.name}/{rec.name}.git"

    def _compute_local_path(self):
        for rec in self:
            rec.local_path = (
                f"/tmp/{rec.forge_id.hostname}/{rec.account_id.name}/{rec.name}"
            )

    def clone(self):
        self.ensure_one()
        user = self.user_id or self.env.user
        user.load_ssh_key()
        try:
            git.Repo.clone_from(self.ssh_url, self.local_path)
            self.status = "cloned"
        except Exception as e:
            _logger.error(f"Failed to clone repository: {e}")
            self.cmd_output = f"Failed to clone repository: {e}"
        finally:
            user.clear_ssh_key()

    def init_repository(self):
        self.ensure_one()
        try:
            subprocess.run(["git", "init", self.local_path], check=True)
            self.status = "initialized"
        except subprocess.CalledProcessError as e:
            _logger.error(f"Failed to initialize Git repository: {e}")
            self.cmd_output = f"Failed to initialize Git repository: {e}"

    def execute_command(self):
        self.ensure_one()
        cmd_list = self.cmd.split()
        if self.cmd == "commit":
            cmd_list.append(self.cmd_input)
        try:
            result = subprocess.run(
                cmd_list,
                cwd=self.local_path,
                check=True,
                capture_output=True,
                text=True,
            )
            self.cmd_output = result.stdout
        except subprocess.CalledProcessError as e:
            _logger.error(f"Failed to execute command {self.cmd}: {e}")
            self.cmd_output = f"Failed to execute command {self.cmd}: {e.stderr}"
