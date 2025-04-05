import logging
import subprocess

from odoo import fields, models

_logger = logging.getLogger(__name__)


class HelmRepo(models.Model):
    _name = "helm.repo"
    _description = "Helm Repo"

    name = fields.Char()
    url = fields.Char()
    state = fields.Selection(
        selection=[("draft", "Draft"), ("active", "Active")],
        default="draft",
    )


import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class HelmRepo(models.Model):
    _name = "helm.repo"
    _description = "Helm Repo"

    name = fields.Char()
    url = fields.Char()
    state = fields.Selection(
        selection=[("draft", "Draft"), ("ready", "Ready"), ("installed", "Installed")],
        default="draft",
    )

    def add_repo(self):
        """
        Add the Kubernetes Build repo using Helm.
        """
        subprocess.run(
            ["helm", "repo", "add", self.name, self.url],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.write({"state": "ready"})

    def install_chart(self):
        """
        Install the Postgres and Odoo release.
        """
        subprocess.run(
            ["helm", "install", "postgres", f"{self.name}/postgres"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        subprocess.run(
            ["helm", "install", "odoo", f"{self.name}/odoo"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.write({"state": "installed"})

    def uninstall_chart(self):
        """
        Uninstall the Postgres and Odoo release.
        """
        subprocess.run(
            ["helm", "uninstall", "postgres"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        subprocess.run(
            ["helm", "uninstall", "odoo"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.write({"state": "ready"})
