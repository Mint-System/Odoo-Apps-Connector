import logging
import subprocess

from odoo import _, fields, models
from .ir_actions_client import display_notification

_logger = logging.getLogger(__name__)


class HelmRelease(models.Model):
    _name = "helm.release"
    _description = "Helm Release"

    name = fields.Char()
    product_id = fields.Many2one("product.product")
    chart_id = fields.Many2one("helm.chart")
    context_id = fields.Many2one("kubectl.context")
    partner_id = fields.Many2one("res.partner", string="Customer")
    state = fields.Selection(
        selection=[("draft", "Draft"), ("installed", "Installed")],
        default="draft",
    )

    def action_install(self):
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
                return display_notification(_("Chart Installed"), output.stdout, "success")
            except subprocess.CalledProcessError as e:
                return display_notification(_("Installing Chart Failed"), e.stderr, "danger")

    def action_upgrade(self):
        """
        Upgrade the Helm chart using the current context configuration.
        """
        self.ensure_one()
        with self.context_id.get_config_path() as config_path:
            try:
                output = subprocess.run(
                    [
                        "helm",
                        "--kubeconfig",
                        config_path,
                        "upgrade",
                        self.name,
                        f"{self.chart_id.repo_id.name}/{self.chart_id.name}",
                    ],
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                self.write({"state": "draft"})
                return display_notification(_("Chart Upgraded"), output.stdout, "success")
            except subprocess.CalledProcessError as e:
                return display_notification(_("Upgrading Chart Failed"), e.stderr, "danger")

    def action_uninstall(self):
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
                return display_notification(_("Chart Uninstalled"), output.stdout, "success")
            except subprocess.CalledProcessError as e:
                return display_notification(_("Uninstalling Chart Failed"), e.stderr, "danger")
