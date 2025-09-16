import logging
import subprocess

import yaml

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools.safe_eval import safe_eval

from .ir_actions_client import display_notification

_logger = logging.getLogger(__name__)


class HelmRelease(models.Model):
    _name = "helm.release"
    _description = "Helm Release"

    name = fields.Char(help="Name of the release.", required=True)
    chart_id = fields.Many2one("helm.chart", help="Chart that shall be installed.", required=True)
    context_id = fields.Many2one("kubectl.context", help="Context used for installation.", required=True)
    create_namespace = fields.Boolean()
    namespace = fields.Char()
    namespace_id = fields.Many2one("kubectl.namespace", string="Linked Namespace", help="Target namespace in cluster.")
    partner_id = fields.Many2one("res.partner", string="Customer")
    state = fields.Selection(
        selection=[("draft", "Draft"), ("installed", "Installed")],
        default="draft",
    )
    values = fields.Text(compute="_compute_values", store=True, string="Custom values.yaml")

    ingress_url = fields.Char(compute="_compute_ingress_url")

    def _get_eval_context(self):
        """
        This eval context can be accessed by the value python expressions.
        """
        return {"self": self, "release": self}

    @api.depends("chart_id", "chart_id.value_ids", "state")
    def _compute_values(self):
        """
        Evaluate custom values of the chart.
        """
        for release in self:
            if release.state == "draft" and release.chart_id.state == "added":
                dict_values = {}
                for value in release.chart_id.value_ids:
                    if safe_eval(value.apply, release._get_eval_context()):
                        try:
                            new_value = safe_eval(value.value, release._get_eval_context())

                            # Apply to release field
                            if value.field_id:
                                release[value.field_id.name] = new_value

                            # Apply to path
                            if value.path:
                                dict_values[value.path] = new_value

                        except Exception as e:
                            raise ValidationError(f"Invalid expression {value.value}: {str(e)}")
                try:
                    release.values = yaml.safe_dump(dict_values, sort_keys=False)
                except yaml.YAMLError as e:
                    raise ValidationError(f"Error converting to YAML: {str(e)}")

    def _compute_ingress_url(self):
        for release in self:
            if release.state == "installed" and release.namespace_id:
                release.ingress_url = (
                    "https://" + release.namespace_id.name + "." + release.context_id.cluster_id.domain
                )
            else:
                release.ingress_url = ""

    def _apply_values(self):
        """
        Apply the custom values and chart values.
        """
        for release in self:
            chart_values = release.chart_id.values  # This is a YAML string
            try:
                dict_values = yaml.safe_load(chart_values) or {}
            except yaml.YAMLError as e:
                raise ValidationError(f"Invalid YAML: {str(e)}")

            for value in release.chart_id.value_ids:
                if safe_eval(value.apply, release._get_eval_context()):
                    try:
                        new_value = safe_eval(value.value, release._get_eval_context())

                        # Apply to release field
                        if value.field_id:
                            release[value.field_id.name] = new_value

                        def set_value(dict_values, path_parts, new_value):
                            part = path_parts[0]
                            if not isinstance(dict_values[part], dict):
                                dict_values[part] = new_value
                            else:
                                path_parts.pop(0)
                                set_value(dict_values[part], path_parts, new_value)

                        # Apply to path of values.yaml
                        if value.path:
                            path_parts = value.path.split(".")
                            set_value(dict_values, path_parts, new_value)

                    except Exception as e:
                        raise ValidationError(f"Invalid expression {value.value}: {str(e)}")

            try:
                release.values = yaml.safe_dump(dict_values, sort_keys=False)
            except yaml.YAMLError as e:
                raise ValidationError(f"Error converting to YAML: {str(e)}")

    def action_install(self):
        """
        Install the Helm chart using the current context configuration.
        """
        self.ensure_one()

        # Check if chart has been added
        if self.chart_id.state != "added":
            raise ValidationError(_(f"The chart '{self.chart_id.name}' has not been added."))

        # Apply custom values
        self._apply_values()

        try:
            command = ["helm", "install", self.name, f"{self.chart_id.repo_id.name}/{self.chart_id.name}"]
            if self.create_namespace:
                command += ["--create-namespace", "--namespace", self.namespace]
            result = self.context_id.run(command, self.values)
            if self.create_namespace and not self.namespace_id:
                self.namespace_id = self.env["kubectl.namespace"].create(
                    {"name": self.namespace, "cluster_id": self.context_id.cluster_id.id}
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
