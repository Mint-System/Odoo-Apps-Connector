import logging
import subprocess

from odoo import _, fields, models
from .ir_actions_client import display_notification

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
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Repo Added"),
                    "type": "success",
                    "message": output.stdout,
                    "next": {
                        "type": "ir.actions.client",
                        "tag": "reload",
                    },
                },
            }
        except subprocess.CalledProcessError as e:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Adding Repo Failed"),
                    "type": "danger",
                    "message": e.stderr,
                },
            }

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
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Repo Updated"),
                    "type": "success",
                    "message": output.stdout,
                    "next": {
                        "type": "ir.actions.client",
                        "tag": "reload",
                    },
                },
            }
        except subprocess.CalledProcessError as e:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Updating Repo Failed"),
                    "type": "danger",
                    "message": e.stderr,
                },
            }

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
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Repo Removed"),
                    "type": "success",
                    "message": output.stdout,
                    "next": {
                        "type": "ir.actions.client",
                        "tag": "reload",
                    },
                },
            }
        except subprocess.CalledProcessError as e:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Removing Repo Failed"),
                    "type": "danger",
                    "message": e.stderr,
                },
            }
