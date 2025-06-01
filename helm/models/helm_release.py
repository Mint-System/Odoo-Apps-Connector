import logging
import subprocess

import yaml

from odoo import _, api, exceptions, fields, models
from odoo.tools import safe_eval

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
    values = fields.Text(compute="_compute_values", store=True, help="Shows Chart values with applied rules.")

    @api.depends("name", "chart_id", "chart_id.edit_ids", "context_id", "partner_id")
    def _compute_values(self):
        for release in self:
            if release.state == "draft":
                release.values = self._apply_edits()

    def _apply_edits(self):
        """
        Apply the value edits to the Chart values template using YAML.
        """
        for release in self:
            values = release.chart_id.values  # This is a YAML string
            edits = release.chart_id.edit_ids

            try:
                dict_values = yaml.safe_load(values) or {}
            except yaml.YAMLError as e:
                raise exceptions.ValidationError(f"Invalid YAML: {str(e)}")

            for edit in edits:
                try:
                    eval_context = {"release": release}
                    new_value = safe_eval.safe_eval(edit.code, eval_context, dict_values)

                    path_parts = edit.path.split(".")
                    target = dict_values
                    for part in path_parts[:-1]:
                        target = target.setdefault(part, {})
                    target[path_parts[-1]] = new_value

                except Exception as e:
                    raise exceptions.ValidationError(f"Invalid expression {edit.code}: {str(e)}")

            try:
                release.values = yaml.safe_dump(dict_values, sort_keys=False)
            except yaml.YAMLError as e:
                raise exceptions.ValidationError(f"Error converting to YAML: {str(e)}")

            return release.values

    def action_install(self):
        """
        Install the Helm chart using the current context configuration.
        """
        self.ensure_one()
        try:
            result = self.context_id.run(
                ["helm", "install", self.name, f"{self.chart_id.repo_id.name}/{self.chart_id.name}"]
            )
            self.write({"state": "installed"})
            return display_notification(_("Chart Installed"), result.stdout, "success")
        except subprocess.CalledProcessError as e:
            return display_notification(_("Installing Chart Failed"), e.stderr, "danger")

    def action_upgrade(self):
        """
        Upgrade the Helm chart using the current context configuration.
        """
        self.ensure_one()
        try:
            result = self.context_id.run(
                [
                    "helm",
                    "upgrade",
                    self.name,
                    f"{self.chart_id.repo_id.name}/{self.chart_id.name}",
                ]
            )
            self.write({"state": "draft"})
            return display_notification(_("Chart Upgraded"), result.stdout, "success")
        except subprocess.CalledProcessError as e:
            return display_notification(_("Upgrading Chart Failed"), e.stderr, "danger")

    def action_uninstall(self):
        """
        Uninstall the Helm chart using the current context configuration.
        """
        self.ensure_one()
        try:
            result = self.context_id.run(
                [
                    "helm",
                    "uninstall",
                    self.name,
                ]
            )
            self.write({"state": "draft"})
            return display_notification(_("Chart Uninstalled"), result.stdout, "success")
        except subprocess.CalledProcessError as e:
            return display_notification(_("Uninstalling Chart Failed"), e.stderr, "danger")
