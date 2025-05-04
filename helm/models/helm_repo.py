import logging
import subprocess

from odoo import _, fields, models

_logger = logging.getLogger(__name__)


class HelmRepo(models.Model):
    _name = "helm.repo"
    _description = "Helm Repo"

    name = fields.Char()
    url = fields.Char()
    state = fields.Selection(
        selection=[("draft", "Draft"), ("added", "Added")],
        default="draft",
    )

    def action_add(self):
        self.ensure_one()
        try:
            output = subprocess.run(
                ["helm", "repo", "add", self.name, self.url],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            self.write({"state": "added"})
            return display_notification(_("Repo Added"), output.stdout, "success")
        except subprocess.CalledProcessError as e:
            return display_notification(_("Adding Repo Failed"), e.stderr, "danger")

    def action_update(self):
        self.ensure_one()
        try:
            output = subprocess.run(
                ["helm", "repo", "update", self.name, self.url],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            return display_notification(_("Repo Updated"), output.stdout, "success")
        except subprocess.CalledProcessError as e:
            return display_notification(_("Updating Repo Failed"), e.stderr, "danger")

    def action_remove(self):
        self.ensure_one()
        try:
            output = subprocess.run(
                [
                    "helm",
                    "repo",
                    "remove",
                    self.name,
                ],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            self.write({"state": "draft"})
            return display_notification(_("Repo Removed"), output.stdout, "success")
        except subprocess.CalledProcessError as e:
            return display_notification(_("Removing Repo Failed"), e.stderr, "danger")
