import logging
import subprocess

from odoo import _, fields, models

from .ir_actions_client import display_notification

_logger = logging.getLogger(__name__)


class HelmRepo(models.Model):
    _name = "helm.repo"
    _description = "Helm Repo"

    name = fields.Char(required=True)
    url = fields.Char(required=True)
    state = fields.Selection(
        selection=[("draft", "Draft"), ("added", "Added")],
        default="draft",
    )

    def _run(self, command):
        return subprocess.run(
            command,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

    def action_add(self):
        self.ensure_one()
        try:
            result = self._run(["helm", "repo", "add", self.name, self.url])
            self.write({"state": "added"})
            return display_notification(_("Repo Added"), result.stdout, "success")
        except subprocess.CalledProcessError as e:
            return display_notification(_("Adding Repo Failed"), e.stderr, "danger")

    def action_update(self):
        self.ensure_one()
        try:
            result = self._run(["helm", "repo", "update", self.name])
            return display_notification(_("Repo Updated"), result.stdout, "success")
        except subprocess.CalledProcessError as e:
            return display_notification(_("Updating Repo Failed"), e.stderr, "danger")

    def action_remove(self):
        self.ensure_one()
        try:
            result = self._run(
                [
                    "helm",
                    "repo",
                    "remove",
                    self.name,
                ]
            )
            self.write({"state": "draft"})
            return display_notification(_("Repo Removed"), result.stdout, "success")
        except subprocess.CalledProcessError as e:
            return display_notification(_("Removing Repo Failed"), e.stderr, "danger")
