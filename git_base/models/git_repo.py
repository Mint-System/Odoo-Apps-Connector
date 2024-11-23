import logging
import os
import re
from subprocess import check_output, run

from odoo import api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class GitRepo(models.Model):
    _name = "git.repo"
    _description = "Git Repo"

    READONLY_STATES = {
        "draft": [("readonly", False)],
        "initialized": [("readonly", True)],
        "cloned": [("readonly", True)],
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
            ("cloned", "Cloned"),
            ("deleted", "Deleted"),
        ],
        default="draft",
        readonly=True,
    )

    cmd_id = fields.Many2one("git.repo.cmd", string="Command")
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

    @api.depends("forge_id", "name")
    def _compute_ssh_url(self):
        for rec in self:
            rec.ssh_url = f"git@{rec.forge_id.hostname}:{rec.name}/{rec.name}.git"

    @api.depends("ssh_url")
    def _compute_remote_url(self):
        for rec in self:
            rec.push_url = f"{rec.ssh_url}"
            rec.pull_url = f"{rec.ssh_url}"

    def _compute_local_path(self):
        for rec in self:
            rec.local_path = f"{rec.account_id.local_path}/{rec.name}"

    def ensure_local_path_exists(self):
        self.ensure_one()
        if not os.path.exists(self.local_path):
            os.makedirs(self.local_path)

    def _inverse_cmd_input_file(self):
        """Store file in local path. If file is zip then extract it."""
        for rec in self:
            if rec.cmd_input_file:
                rec.ensure_local_path_exists()
                with open(
                    os.path.join(rec.local_path, rec.cmd_input_filename), "wb"
                ) as f:
                    f.write(rec.cmd_input_file)
                    if rec.cmd_input_filename.endswith(".zip"):
                        run(
                            [
                                "unzip",
                                os.path.join(rec.local_path, rec.cmd_input_filename),
                            ],
                            check=True,
                        )
                    rec.cmd_input_file = False
                    rec.cmd_input_filename = False

    def action_run_cmd(self):
        self.ensure_one()
        if self.cmd_id:
            getattr(self, "cmd_" + self.cmd_id.name)()
        self.cmd_id = False

    def cmd_init(self):
        self.ensure_local_path_exists()
        output = check_output(["git", "init", "-b", "main", self.local_path])
        self.write(
            {
                "cmd_output": output,
                "state": "initialized",
                "branch_ids": [(0, 0, {"name": "main", "repo_id": self.id})],
            }
        )

    def cmd_status(self):
        self.ensure_local_path_exists()
        output = check_output(["git", "-C", self.local_path, "status"])
        self.write({"cmd_output": output})

    def cmd_remove(self):
        output = check_output(["rm", "-rf", self.local_path])
        self.write({"cmd_output": output, "state": "deleted"})
        self.branch_ids.unlink()
