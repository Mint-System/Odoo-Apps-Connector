import logging
import os
import subprocess
import tempfile
from contextlib import contextmanager

from odoo import _, fields, models

_logger = logging.getLogger(__name__)


class KubectlContext(models.Model):
    _name = "kubectl.context"
    _description = "Kubectl Context"

    name = fields.Char()
    cluster_id = fields.Many2one("kubectl.cluster")
    config = fields.Text("config")
    is_current = fields.Boolean(compute="_compute_is_current")

    def _compute_is_current(self):
        for rec in self:
            rec.is_current = self.env.user.current_context_id == rec

    def action_use_context(self):
        self.ensure_one()
        self.env.user.current_context_id = self

    @contextmanager
    def get_config_path(self):
        """
        Context manager that creates a temporary file with kubectl config.

        Yields:
            str: Path to the temporary config file
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

    def action_test_connection(self):
        """
        Test connection to the kubernetes cluster using this context.
        """
        self.ensure_one()

        with self.get_config_path() as config_path:
            try:
                output = subprocess.run(
                    ["kubectl", "--kubeconfig", config_path, "cluster-info"],
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )

                return {
                    "type": "ir.actions.client",
                    "tag": "display_notification",
                    "params": {
                        "title": _("Connection Success"),
                        "type": "success",
                        "message": output.stdout,
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
