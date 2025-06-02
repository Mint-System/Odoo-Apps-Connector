import logging
import os
import subprocess
import tempfile
from contextlib import contextmanager

from odoo import _, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class KubectlContext(models.Model):
    _name = "kubectl.context"
    _description = "Kubectl Context"

    name = fields.Char()
    cluster_id = fields.Many2one("kubectl.cluster")
    namespace_id = fields.Many2one("kubectl.namespace")
    config = fields.Text(help="Export and pase config with `kubectl config view --minify --raw`.")
    is_current = fields.Boolean(compute="_compute_is_current")
    command = fields.Char(help="Run a command that starts with `kubectl` or `helm`.")
    output = fields.Text(help="Output of the command.")

    def _compute_is_current(self):
        result = subprocess.run(
            ["kubectl", "config", "current-context"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for rec in self:
            rec.is_current = True if rec.name == result.stdout.strip() else False

    def action_run(self):
        """
        Run a command.
        """
        self.ensure_one()
        if not self.command or not (self.command.startswith("kubectl ") or self.command.startswith("helm ")):
            raise ValidationError(_("Command must start with either `kubectl` or `helm`."))

        command = self.command.split(" ")
        try:
            result = self.run(command)
            self.output = result.stdout
        except subprocess.CalledProcessError as e:
            self.output = e.stderr

    @contextmanager
    def get_config_path(self):
        """
        Context manager that creates a temporary file with kubectl config.
        """
        self.ensure_one()

        # Write config to temporary file
        with tempfile.NamedTemporaryFile(mode="w+", delete=False) as temp_file:
            temp_file.write(self.config)
            temp_file_path = temp_file.name

        try:
            yield temp_file_path
        finally:
            # Clean up the temporary file
            os.unlink(temp_file_path)

    def run(self, command):
        """
        Run kubectl or helm command.
        """
        self.ensure_one()

        # If config is given apply kubeconfig
        if self.config:
            with self.get_config_path() as config_path:
                command = command[0] + ["--kubeconfig", config_path] + command[1:]

        # Apply context explicitlty
        if command[0] == "kubectl":
            command.extend([f"--context={self.name}"])
        if command[0] == "helm":
            command.extend(["--kube-context", self.name])

        _logger.warning("Run command: %s", command)
        return subprocess.run(
            command,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

    def action_use_context(self):
        """
        Change kube context.
        """
        self.ensure_one()
        try:
            result = self.run(["kubectl", "config", "use-context", self.name])
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Use Context Success"),
                    "type": "success",
                    "message": result.stdout,
                },
            }
        except subprocess.CalledProcessError as e:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Use Context Failed"),
                    "type": "danger",
                    "message": e.stderr,
                },
            }

    def action_test_connection(self):
        """
        Test connection to the kubernetes cluster using this context.
        """
        self.ensure_one()
        try:
            result = self.run(["kubectl", "cluster-info"])
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Connection Success"),
                    "type": "success",
                    "message": result.stdout,
                },
            }
        except subprocess.CalledProcessError as e:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Connection Failed"),
                    "type": "danger",
                    "message": e.stderr,
                },
            }
