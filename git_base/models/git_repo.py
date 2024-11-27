import base64
import io
import logging
import os
import re
import zipfile
from subprocess import STDOUT, CalledProcessError, check_output, run

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

    # Repo fields

    name = fields.Char(required=True, states=READONLY_STATES)
    http_url = fields.Char(
        string="HTTP Url", compute="_compute_http_url", readonly=True
    )
    ssh_url = fields.Char(
        string="SSH Url", compute="_compute_ssh_url", store=True, readonly=True
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

    def _compute_http_url(self):
        for rec in self:
            rec.http_url = f"{rec.account_id.http_url}/{rec.name}"

    @api.depends("forge_id", "account_id", "name")
    def _compute_ssh_url(self):
        for rec in self:
            rec.ssh_url = (
                f"git@{rec.forge_id.hostname}:{rec.account_id.name}/{rec.name}.git"
            )

    @api.constrains("ssh_url")
    def _validate_ssh_url(self):
        for rec in self:
            if rec.ssh_url and not re.match(
                r"((git|ssh|http(s)?)|(git@[\w\.]+))(:(//)?)([\w\.@\:/\-~]+)(\.git)(/)?",
                rec.ssh_url,
            ):
                raise ValidationError(f"Invalid SSH url: {rec.ssh_url}.")

    def _compute_local_path(self):
        for rec in self:
            rec.local_path = f"{rec.account_id.local_path}/{rec.name}"

    def _compute_ref(self):
        for rec in self:
            if rec.active_branch_id:
                rec.ref = rec.active_branch_id.name
            else:
                rec.ref = self._get_git_branch_name()

    # Command fields

    def _get_default_cmd_id(self):
        if self.state in ["initialized", "connected"]:
            return self.env.ref("git_base.cmd_status")
        else:
            return self.env.ref("git_base.cmd_init")

    cmd_id = fields.Many2one(
        "git.repo.cmd", string="Command", default=_get_default_cmd_id
    )
    cmd_help = fields.Char(related="cmd_id.help")
    show_input = fields.Boolean(related="cmd_id.show_input")
    cmd_input = fields.Text("Input")
    cmd_input_file = fields.Binary(
        "File Upload",
        inverse="_inverse_cmd_input_file",
        help="Upload file to local path. Zip file will be extracted.",
    )
    cmd_input_filename = fields.Char("Filename")
    cmd_input_folder_path = fields.Char("Upload Path", default="./")
    cmd_output = fields.Text("Output", readonly=True)

    def _inverse_cmd_input_file(self):
        """Store file in local path. If file is zip then extract it."""
        for rec in self:
            if rec.cmd_input_file:
                rec.ensure_local_path_exists()

                upload_path = rec.local_path
                if rec.cmd_input_folder_path:
                    upload_path = os.path.join(upload_path, rec.cmd_input_folder_path)

                if not os.path.exists(upload_path):
                    raise UserError(_("Upload path does not exist."))

                if rec.cmd_input_filename.endswith(".zip"):
                    with zipfile.ZipFile(
                        io.BytesIO(base64.decodebytes(rec.cmd_input_file))
                    ) as zip_file:
                        zip_file.extractall(upload_path)
                else:
                    with open(
                        os.path.join(upload_path, rec.cmd_input_filename), "wb"
                    ) as file:
                        file.write(base64.decodebytes(rec.cmd_input_file))
                rec.cmd_input_file = False
                rec.cmd_input_filename = False

    # Branch fields

    branch_ids = fields.One2many("git.repo.branch", "repo_id")
    account_id = fields.Many2one("git.account", required=True, states=READONLY_STATES)
    forge_id = fields.Many2one("git.forge", related="account_id.forge_id")

    # Configuration fields

    push_url = fields.Char(
        compute="_compute_remote_url", store=True, states=READONLY_STATES
    )
    pull_url = fields.Char(
        compute="_compute_remote_url", store=True, states=READONLY_STATES
    )
    user_id = fields.Many2one("res.users")
    ssh_public_key = fields.Char("SSH Public Key")
    ssh_private_key_file = fields.Binary("SSH Private Key")
    ssh_private_key_filename = fields.Char(
        "SSH Private Key Filename", compute="_compute_ssh_private_key_filename"
    )
    ssh_private_key_password = fields.Char("SSH Private Key Password")

    def _compute_ssh_private_key_filename(self):
        for user in self:
            user.ssh_private_key_filename = f"/tmp/user_private_key_{self.id}"

    @api.depends("ssh_url")
    def _compute_remote_url(self):
        for rec in self:
            rec.push_url = f"{rec.ssh_url}"
            rec.pull_url = f"{rec.ssh_url}"

    # Model methods

    @api.model
    def switch_to_environment_branch(self):
        environment_id = self.env["server.config.environment"].get_active_environment()
        branch_id = self.branch_ids.filtered(
            lambda b: b.environment_id == environment_id
        )
        if not branch_id:
            raise UserError(
                _("No branch found for environment: %s") % environment_id.name
            )
        self.cmd_switch(branch_id.name)

    def ensure_local_path_exists(self):
        self.ensure_one()
        if not os.path.exists(self.local_path):
            os.makedirs(self.local_path)

    def unlink(self):
        for rec in self:
            if not rec.state == "deleted":
                raise UserError(_("Repo can only be deleted if is in state 'Deleted'."))
        return super().unlink()

    def _get_git_user(self):
        return self.user_id or self.env.user

    def _get_keychain(self):
        # Return keychain in order: deploy > user > personal
        if self.ssh_private_key_file:
            return self
        else:
            return self._get_git_user()

    def _get_git_author(self):
        user = self._get_git_user()
        return f"{user.name} <{user.email}>"

    def _get_git_branch_list(self):
        self.ensure_one()
        if os.path.exists(f"{self.local_path}"):
            return (
                check_output(["git", "-C", self.local_path, "branch", "--list"])
                .decode("utf-8")
                .replace("* ", "")  # Active branch is marked with *
                .strip()  # Remove newlines
            ).split("\n")
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

    def _set_output(self, output):
        """
        Reset input fields and set output.
        """
        if self.cmd_id.next_command_id:
            self.cmd_id = self.cmd_id.next_command_id
        else:
            self.cmd_id = self._get_default_cmd_id()
        if self.cmd_id.clear_input:
            self.cmd_input = False
        self.write({"cmd_output": output})

    def action_run_cmd(self):
        """Run selected command reset defaults."""
        self.ensure_one()
        if self.cmd_id:
            _logger.info("Running git command: cmd_%s", self.cmd_id.code)
            getattr(self, "cmd_" + self.cmd_id.code)()

    def action_generate_deploy_keys(self):
        self.ensure_one()
        ssh_keygen_command = [
            "ssh-keygen",
            "-t",
            "ed25519",
            "-C",
            f"{self.account_id.name}-{self.name}@{self.forge_id.hostname}",
            "-f",
            f"{self.ssh_private_key_filename}",
            "-N",
            self.ssh_private_key_password or "",
        ]
        run(ssh_keygen_command)

        # Store public key
        with open(f"{self.ssh_private_key_filename}.pub", "r") as file:
            self.write({"ssh_public_key": file.read()})

        # Store private key
        with open(f"{self.ssh_private_key_filename}", "rb") as file:
            self.write({"ssh_private_key_file": base64.b64encode(file.read())})

        os.remove(f"{self.ssh_private_key_filename}.pub")
        os.remove(f"{self.ssh_private_key_filename}")

    def run_ssh_command(self, git_command):
        """Context manager to set up the SSH environment for Git operations."""

        keychain = self._get_keychain()
        if keychain.ssh_private_key_file:
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
                    self.ssh_private_key_filename,
                ]
                # _logger.warning(" ".join(ssh_add_command))
                output = check_output(ssh_add_command, stderr=STDOUT, timeout=5)

                os.environ[
                    "GIT_SSH_COMMAND"
                ] = f"ssh -o StrictHostKeyChecking=no -i {self.ssh_private_key_filename}"
                # _logger.warning(" ".join(git_command))
                output += check_output(git_command, stderr=STDOUT, timeout=5)
                return output
            except CalledProcessError as e:
                raise Exception(e.output)
            finally:
                os.remove(keychain.ssh_private_key_filename)
        return "Missing SSH private key."

    # Status Commands

    def cmd_status(self):
        self.ensure_one()
        output = check_output(["git", "-C", self.local_path, "status"], stderr=STDOUT)
        self._set_output(output)

    def cmd_log(self):
        self.ensure_one()
        output = check_output(["git", "-C", self.local_path, "log"], stderr=STDOUT)
        self._set_output(output)

    def cmd_list(self):
        self.ensure_one()
        list_path = self.local_path
        if self.cmd_input:
            list_path = os.path.join(self.local_path, self.cmd_input)
        output = check_output(["ls", "-a", list_path], stderr=STDOUT)
        self._set_output(output)

    # Stage Commands

    def cmd_add_all(self):
        self.ensure_one()
        output = check_output(
            ["git", "-C", self.local_path, "add", "--all"], stderr=STDOUT
        )
        self._set_output(output)

    def cmd_unstage_all(self):
        self.ensure_one()
        output = check_output(
            ["git", "-C", self.local_path, "restore", "--staged", "."], stderr=STDOUT
        )
        self._set_output(output)

    def cmd_clean(self):
        self.ensure_one()
        output = check_output(
            ["git", "-C", self.local_path, "clean", "-fd"], stderr=STDOUT
        )
        self._set_output(output)

    def cmd_reset_hard(self):
        self.ensure_one()
        output = check_output(
            ["git", "-C", self.local_path, "reset", "--hard"], stderr=STDOUT
        )
        self._set_output(output)

    def cmd_diff(self):
        self.ensure_one()
        output = check_output(["git", "-C", self.local_path, "diff"], stderr=STDOUT)
        self._set_output(output)

    def cmd_commit(self):
        self.ensure_one()
        if not self.cmd_input:
            raise UserError(_("Missing commit message."))
        user = self._get_git_user()
        os.environ["GIT_COMMITTER_NAME"] = user.name
        os.environ["GIT_COMMITTER_EMAIL"] = user.email
        git_command = [
            "git",
            "-C",
            self.local_path,
            "commit",
            "--author",
            self._get_git_author(),
            "-m",
            self.cmd_input,
            "--no-gpg-sign",
        ]
        output = self.run_ssh_command(git_command)
        self._set_output(output)

    def cmd_commit_all(self):
        self.ensure_one()
        if not self.cmd_input:
            raise UserError(_("Missing commit message."))
        user = self._get_git_user()
        os.environ["GIT_COMMITTER_NAME"] = user.name
        os.environ["GIT_COMMITTER_EMAIL"] = user.email
        git_command = [
            "git",
            "-C",
            self.local_path,
            "commit",
            "--author",
            self._get_git_author(),
            "-a",
            "-m",
            self.cmd_input,
            "--no-gpg-sign",
        ]
        output = check_output(git_command, stderr=STDOUT)
        self._set_output(output)

    # Branch Commands

    def cmd_branch_list(self):
        self.ensure_one()
        branch_list = "\n".join(self._get_git_branch_list())
        self.write({"cmd_output": branch_list})

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
        self.write({"active_branch_id": branch_id})
        self._set_output(output)

    def cmd_delete_branch(self, branch_name):
        self.ensure_one()
        if not branch_name:
            branch_name = self.cmd_input
        if not branch_name:
            raise UserError(_("Missing branch name."))

        # Get branch record
        branch_id = self.branch_ids.filtered(lambda b: b.name == branch_name)

        # Check if branch is not active
        if self.active_branch_id == branch_id:
            raise UserError(_("Cannot remove active branch."))

        # If branch exists in git, delete
        git_branch_list = self._get_git_branch_list()
        if branch_name in git_branch_list:
            output = check_output(
                ["git", "-C", self.local_path, "branch", "-D", branch_name],
                stderr=STDOUT,
            )
            self._set_output(output)

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
        self.write({"state": "connected"})
        self._set_output(output)

    def cmd_set_upstream(self):
        self.ensure_one()
        output = self.run_ssh_command(
            [
                "git",
                "-C",
                self.local_path,
                "branch",
                f"--set-upstream-to=origin/{self.active_branch_id.name}",
                self.active_branch_id.name,
            ]
        )
        self._set_output(output)
        self.active_branch_id.write(
            {"upstream": f"origin/{self.active_branch_id.name}"}
        )

    def cmd_pull(self):
        self.ensure_one()
        output = self.run_ssh_command(
            [
                "git",
                "-C",
                self.local_path,
                "pull",
                "origin",
                self.active_branch_id.name,
            ]
        )
        self._set_output(output)

    def cmd_push(self):
        self.ensure_one()
        output = self.run_ssh_command(["git", "-C", self.local_path, "push"])
        self._set_output(output)

    def cmd_push_upstream(self):
        self.ensure_one()
        output = self.run_ssh_command(
            [
                "git",
                "-C",
                self.local_path,
                "push",
                "--set-upstream",
                "origin",
                self.active_branch_id.name,
            ]
        )
        self._set_output(output)
        self.active_branch_id.write(
            {"upstream": f"origin/{self.active_branch_id.name}"}
        )

    # Repo Commands

    def cmd_init(self):
        self.ensure_local_path_exists()
        output = check_output(["git", "init", self.local_path], stderr=STDOUT)
        branch_name = self._get_git_branch_name()
        self.write(
            {
                "state": "initialized",
            }
        )
        self.active_branch_id = self.env["git.repo.branch"].create(
            {"name": branch_name, "repo_id": self.id}
        )
        self._set_output(output)

    def cmd_clone(self):
        self.ensure_one()
        output = self.run_ssh_command(["git", "clone", self.ssh_url, self.local_path])
        branch_name = self._get_git_branch_name()
        self.write(
            {
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
        self._set_output(output)

    def cmd_remove(self):
        self.ensure_one()
        remove_path = self.local_path
        if self.cmd_input:
            remove_path = os.path.join(self.local_path, self.cmd_input)
        output = check_output(["rm", "-rf", remove_path], stderr=STDOUT)
        if self.local_path == remove_path:
            self.write({"state": "deleted", "active_branch_id": False})
            self.branch_ids.unlink()
            self._set_output(output)

    def cmd_mkdir(self):
        self.ensure_one()
        mkdir_path = self.local_path
        if self.cmd_input:
            mkdir_path = os.path.join(self.local_path, self.cmd_input)
        output = check_output(["mkdir", "-p", mkdir_path], stderr=STDOUT)
        self._set_output(output)

    def cmd_ssh_test(self):
        self.ensure_one()
        keychain = self._get_keychain()
        output = self.run_ssh_command(
            [
                "ssh",
                "-i",
                keychain.ssh_private_key_filename,
                "-o",
                "StrictHostKeyChecking=no",
                "-T",
                f"git@{self.forge_id.hostname}",
            ]
        )
        self._set_output(output)
