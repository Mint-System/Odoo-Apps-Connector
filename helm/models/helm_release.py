import logging
import subprocess

from odoo import _, fields, models

_logger = logging.getLogger(__name__)


class HelmRelease(models.Model):
    _name = "helm.release"
    _description = "Helm Release"

    name = fields.Char()
    chart_id = fields.Many2one("helm.chart")
    partner_id = fields.Many2one("res.partner")
    state = fields.Selection(
        selection=[("draft", "Draft"), ("installed", "Installed")],
        default="draft",
    )

    def install(self):
        output = subprocess.run(
            ["helm", "install", f"{self.name}", f"{self.chart_id.repo_id.name}/{self.chart_id.name}"],
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
            },
        }

    def uninstall(self):
        self.ensure_one()
        output = subprocess.run(
            ["helm", "uninstall", self.name],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.write({"state": "draft"})
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Chart Uninstalled"),
                "type": "success",
                "message": output.stdout,
            },
        }
