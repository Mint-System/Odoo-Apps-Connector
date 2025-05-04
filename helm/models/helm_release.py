import logging
import subprocess

from odoo import _, fields, models

_logger = logging.getLogger(__name__)


class HelmRelease(models.Model):
    _name = "helm.release"
    _description = "Helm Release"

    name = fields.Char()
    chart_id = fields.Many2one("helm.chart")
    context_id = fields.Many2one("kubectl.context")
    partner_id = fields.Many2one("res.partner", string="Customer")
    state = fields.Selection(
        selection=[("draft", "Draft"), ("installed", "Installed")],
        default="draft",
    )

    def install(self):
        """
        Install the Helm chart using the current context configuration.
        """
        self.ensure_one()
        with self.context_id.get_config_path() as config_path:
            try:
                output = subprocess.run(
                    [
                        "helm",
                        "--kubeconfig",
                        config_path,
                        "install",
                        self.name,
                        f"{self.chart_id.repo_id.name}/{self.chart_id.name}",
                    ],
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                self.write({"state": "installed"})
                return {
                    "type": "ir.actions.client",
                    "tag": "display_notification",
                    "params": {
                        "title": _("Chart Installed"),
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
                        "title": _("Installation Failed"),
                        "type": "danger",
                        "message": e.stderr,
                    },
                }

    def uninstall(self):
        """
        Uninstall the Helm chart using the current context configuration.
        """
        self.ensure_one()
        with self.context_id.get_config_path() as config_path:
            try:
                output = subprocess.run(
                    ["helm", "--kubeconfig", config_path, "uninstall", self.name],
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
                        "title": _("Chart Uninstalled"),
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
                        "title": _("Uninstallation Failed"),
                        "type": "danger",
                        "message": e.stderr,
                    },
                }
