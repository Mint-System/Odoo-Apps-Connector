import base64
import io
import logging
import os
import re
import zipfile
from subprocess import STDOUT, check_output

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class GitRepo(models.Model):
    _name = "git.repo"
    _description = "Git Repo"

    READONLY_STATES = {
        "draft": [("readonly", False)],
        "initialized": [("readonly", True)],
        "connected": [("readonly", True)],
        "deleted": [("readonly", False)],
    }

    name = fields.Char(required=True, states=READONLY_STATES)
    http_url = fields.Char(
        string="HTTP Url", compute="_compute_http_url", readonly=True
    )
    ssh_url = fields.Char(
        string="SSH Url", compute="_compute_ssh_url", store=True, readonly=True
    )
    push_url = fields.Char(
        compute="_compute_remote_url", store=True, states=READONLY_STATES
    )
    pull_url = fields.Char(
        compute="_compute_remote_url", store=True, states=READONLY_STATES
    )
    local_path = fields.Char(compute="_compute_local_path")
    state = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("initialized", "Initialized"),
            ("connected", "Connected"),
            ("deleted", "Deleted"),
        ],
        default="draft",
        readonly=True,
    )
    ref = fields.Char(readonly=True, compute="_compute_ref")
    active_branch_id = fields.Many2one("git.repo.branch", readonly=True)

    def _get_default_cmd_id(self):
        if self.state in ["initialized", "connected"]:
            return self.env.ref("git_base.cmd_status")
        else:
            return self.env.ref("git_base.cmd_init")

    cmd_id = fields.Many2one(
        "git.repo.cmd", string="Command", default=_get_default_cmd_id
    )
    show_input = fields.Boolean(related="cmd_id.show_input")
    cmd_input = fields.Text("Input")
    cmd_input_file = fields.Binary(
        "File Upload",
        inverse="_inverse_cmd_input_file",
        help="Upload file to local path. Zip file will be extracted.",
    )
    cmd_input_filename = fields.Char("Filename")
    cmd_output = fields.Text("Output", readonly=True)

    user_id = fields.Many2one("res.users")
    branch_ids = fields.One2many("git.repo.branch", "repo_id")
    account_id = fields.Many2one("git.account", required=True, states=READONLY_STATES)
    forge_id = fields.Many2one("git.forge", related="account_id.forge_id")

    @api.constrains("ssh_url")
    def _validate_ssh_url(self):
        for rec in self:
            if rec.ssh_url and not re.match(
                r"((git|ssh|http(s)?)|(git@[\w\.]+))(:(//)?)([\w\.@\:/\-~]+)(\.git)(/)?",
                rec.ssh_url,
            ):
                raise ValidationError(f"Invalid SSH url: {rec.ssh_url}.")

    def _compute_http_url(self):
        for rec in self:
            rec.http_url = f"{rec.account_id.http_url}/{rec.name}"

    @api.depends("forge_id", "account_id", "name")
    def _compute_ssh_url(self):
        for rec in self:
            rec.ssh_url = (
                f"git@{rec.forge_id.hostname}:{rec.account_id.name}/{rec.name}.git"
            )

    @api.depends("ssh_url")
    def _compute_remote_url(self):
        for rec in self:
            rec.push_url = f"{rec.ssh_url}"
            rec.pull_url = f"{rec.ssh_url}"

    def _compute_local_path(self):
        for rec in self:
            rec.local_path = f"{rec.account_id.local_path}/{rec.name}"

    def _compute_ref(self):
        for rec in self:
            if rec.active_branch_id:
                rec.ref = rec.active_branch_id.name
            else:
                rec.ref = self._get_git_branch_name()

    def ensure_local_path_exists(self):
        self.ensure_one()
        if not os.path.exists(self.local_path):
            os.makedirs(self.local_path)

    def _inverse_cmd_input_file(self):
        """Store file in local path. If file is zip then extract it."""
        for rec in self:
            if rec.cmd_input_file:
                rec.ensure_local_path_exists()
                if rec.cmd_input_filename.endswith(".zip"):
                    with zipfile.ZipFile(
                        io.BytesIO(base64.decodebytes(rec.cmd_input_file))
                    ) as zip_file:
                        zip_file.extractall(rec.local_path)
                else:
                    with open(
                        os.path.join(rec.local_path, rec.cmd_input_filename), "wb"
                    ) as file:
                        file.write(rec.cmd_input_file)
                rec.cmd_input_file = False
                rec.cmd_input_filename = False

    def unlink(self):
        for rec in self:
            if not rec.state == "deleted":
                raise UserError(_("Repo can only be deleted if is in state 'Deleted'."))
        return super().unlink()

    @api.model
    def _get_git_user(self):
        return self.user_id or self.env.user

    @api.model
    def _get_git_author(self):
        user = self._get_git_user()
        return f'"{user.name} <{user.email}>"'

    def _get_git_branch_list(self):
        self.ensure_one()
        if os.path.exists(f"{self.local_path}"):
            return (
                check_output(["git", "-C", self.local_path, "branch", "--list"])
                .decode("utf-8")
                .strip()
            )
        else:
            return ""

    def _get_git_branch_name(self):
        self.ensure_one()
        if os.path.exists(f"{self.local_path}/.git"):
            return (
                check_output(["git", "-C", self.local_path, "branch", "--show-current"])
                .decode("utf-8")
                .strip()
            )
        else:
            return ""

    def action_run_cmd(self):
        self.ensure_one()
        if self.cmd_id:
            getattr(self, "cmd_" + self.cmd_id.code)()
        self.cmd_id = self._get_default_cmd_id()

    # Status Commands

    def cmd_status(self):
        self.ensure_one()
        output = check_output(["git", "-C", self.local_path, "status"], stderr=STDOUT)
        self.write({"cmd_output": output})

    def cmd_log(self):
        self.ensure_one()
        output = check_output(["git", "-C", self.local_path, "log"], stderr=STDOUT)
        self.write({"cmd_output": output})

    def cmd_list(self):
        self.ensure_one()
        output = check_output(["ls", "-lsh", self.local_path], stderr=STDOUT)
        self.write({"cmd_output": output})

    # Stage Commands

    def cmd_add_all(self):
        self.ensure_one()
        output = check_output(
            ["git", "-C", self.local_path, "add", "-A"], stderr=STDOUT
        )
        self.write({"cmd_output": output})

    def cmd_unstage_all(self):
        self.ensure_one()
        output = check_output(
            ["git", "-C", self.local_path, "restore", "--staged", "."], stderr=STDOUT
        )
        self.write({"cmd_output": output})

    def cmd_clean(self):
        self.ensure_one()
        output = check_output(
            ["git", "-C", self.local_path, "clean", "-fd"], stderr=STDOUT
        )
        self.write({"cmd_output": output})

    def cmd_reset_hard(self):
        self.ensure_one()
        output = check_output(
            ["git", "-C", self.local_path, "reset", "--hard"], stderr=STDOUT
        )
        self.write({"cmd_output": output})

    def cmd_diff(self):
        self.ensure_one()
        output = check_output(["git", "-C", self.local_path, "diff"], stderr=STDOUT)
        self.write({"cmd_output": output})

    def cmd_commit(self):
        self.ensure_one()
        if not self.cmd_input:
            raise UserError(_("Missing commit message."))
        output = check_output(
            [
                "git",
                "-C",
                self.local_path,
                "commit",
                "--author",
                self._get_git_author(),
                "-m",
                f'"{self.cmd_input}"',
            ],
            stderr=STDOUT,
        )
        self.write({"cmd_output": output, "cmd_input": False})

    def cmd_commit_all(self):
        self.ensure_one()
        if not self.cmd_input:
            raise UserError(_("Missing commit message."))
        try:
            output = check_output(
                [
                    "git",
                    "-C",
                    self.local_path,
                    "commit",
                    "--author",
                    self._get_git_author(),
                    "-a",
                    "-m",
                    f'"{self.cmd_input}"',
                ],
                stderr=STDOUT,
            )
            self.write({"cmd_output": output, "cmd_input": False})
        except Exception as e:
            self.write({"cmd_output": e})

    # Branch Commands

    def cmd_branch_list(self):
        self.ensure_one()
        self.write({"cmd_output": self._get_git_branch_list()})

    def cmd_switch(self, branch_name=None):
        self.ensure_one()
        if not branch_name:
            branch_name = self.cmd_input
        if not branch_name:
            raise UserError(_("Missing branch name."))

        # Get branch record
        branch_id = self.branch_ids.filtered(lambda b: b.name == branch_name)

        # Get list of branches
        git_branch_list = self._get_git_branch_list()

        if branch_id and branch_name in git_branch_list:
            output = check_output(
                ["git", "-C", self.local_path, "switch", branch_name], stderr=STDOUT
            )
        if not branch_id:
            branch_id = self.env["git.repo.branch"].create(
                {"name": branch_name, "repo_id": self.id}
            )
        if branch_name not in git_branch_list:
            output = check_output(
                ["git", "-C", self.local_path, "switch", "-c", branch_name],
                stderr=STDOUT,
            )

        self.write({"cmd_output": output, "active_branch_id": branch_id})

    def cmd_delete_branch(self, branch_name):
        self.ensure_one()
        if not branch_name:
            branch_name = self.cmd_input
        if not branch_name:
            raise UserError(_("Missing branch name."))

        branch_id = self.branch_ids.filtered(lambda b: b.name == branch_name)

        if self.active_branch_id == branch_id:
            raise UserError(_("Cannot remove active branch."))

        git_branch_list = self._get_git_branch_list()

        if branch_name in git_branch_list:
            output = check_output(
                ["git", "-C", self.local_path, "branch", "-D", branch_name],
                stderr=STDOUT,
            )
            self.write({"cmd_output": output})

    # Remote Commands

    def cmd_add_remote(self):
        self.ensure_one()
        output = check_output(
            [
                "git",
                "-C",
                self.local_path,
                "remote",
                "add",
                "origin",
                self.ssh_url,
            ],
            stderr=STDOUT,
        )
        self.write({"cmd_output": output, "state": "connected"})

    def cmd_set_upstream(self):
        self.ensure_one()
        user = self._get_git_user()
        with user.ssh_env() as ssh_env:
            try:
                output = check_output(
                    [
                        "git",
                        "-C",
                        self.local_path,
                        "branch",
                        f"--set-upstream-to=origin/{self.active_branch_id.name}",
                        self.active_branch_id.name,
                    ],
                    env=ssh_env,
                    stderr=STDOUT,
                )
                self.write({"cmd_output": output})
                self.active_branch_id.write(
                    {"upstream": f"origin/{self.active_branch_id.name}"}
                )
            except Exception as e:
                self.write({"cmd_output": e})

    def cmd_pull(self):
        self.ensure_one()
        user = self._get_git_user()
        with user.ssh_env() as ssh_env:
            try:
                output = check_output(
                    [
                        "git",
                        "-C",
                        self.local_path,
                        "pull",
                        "origin",
                        self.active_branch_id.name,
                    ],
                    env=ssh_env,
                    stderr=STDOUT,
                )
                self.write({"cmd_output": output})
            except Exception as e:
                self.write({"cmd_output": e})

    def cmd_push(self):
        self.ensure_one()
        user = self._get_git_user()
        with user.ssh_env() as ssh_env:
            try:
                output = check_output(
                    ["git", "-C", self.local_path, "push"], env=ssh_env, stderr=STDOUT
                )
                self.write({"cmd_output": output})
            except Exception as e:
                self.write({"cmd_output": e})

    def cmd_push_upstream(self):
        self.ensure_one()
        user = self._get_git_user()
        with user.ssh_env() as ssh_env:
            try:
                output = check_output(
                    [
                        "git",
                        "-C",
                        self.local_path,
                        "push",
                        "--set-upstream",
                        "origin",
                        self.active_branch_id.name,
                    ],
                    env=ssh_env,
                    stderr=STDOUT,
                )
                self.write({"cmd_output": output})
                self.active_branch_id.write(
                    {"upstream": f"origin/{self.active_branch_id.name}"}
                )
            except Exception as e:
                self.write({"cmd_output": e})

    # Repo Commands

    def cmd_init(self):
        self.ensure_local_path_exists()
        output = check_output(["git", "init", self.local_path], stderr=STDOUT)
        branch_name = self._get_git_branch_name()
        self.write(
            {
                "cmd_output": output,
                "state": "initialized",
            }
        )
        self.active_branch_id = self.env["git.repo.branch"].create(
            {"name": branch_name, "repo_id": self.id}
        )

    def cmd_clone(self):
        self.ensure_one()
        user = self._get_git_user()
        with user.ssh_env() as ssh_env:
            try:
                output = check_output(
                    ["git", "clone", self.ssh_url, self.local_path],
                    env=ssh_env,
                    stderr=STDOUT,
                )
                branch_name = self._get_git_branch_name()
                self.write(
                    {
                        "cmd_output": output,
                        "state": "connected",
                    }
                )
                self.active_branch_id = self.env["git.repo.branch"].create(
                    {
                        "name": branch_name,
                        "repo_id": self.id,
                        "upstream": f"origin/{branch_name}",
                    }
                )
            except Exception as e:
                self.write({"cmd_output": e})

    def cmd_remove(self):
        self.ensure_one()
        output = check_output(["rm", "-rf", self.local_path], stderr=STDOUT)
        self.write(
            {"cmd_output": output, "state": "deleted", "active_branch_id": False}
        )
        self.branch_ids.unlink()

    def cmd_mkdir(self):
        self.ensure_one()
        output = check_output(["mkdir", "-p", self.local_path], stderr=STDOUT)
        self.write({"cmd_output": output})

    def cmd_ssh_test(self):
        self.ensure_one()
        try:
            user = self._get_git_user()
            output = user.ssh_test(self.forge_id.hostname)
            self.write({"cmd_output": output})
        except Exception as e:
            self.write({"cmd_output": e})
