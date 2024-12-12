import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class Company(models.Model):
    _inherit = "res.company"

    ssh_private_key_file = fields.Binary(
        "SSH Private Key", compute="_compute_ssh_private_key_file"
    )
    ssh_private_key_filename = fields.Char(
        "SSH Private Key Filename", compute="_compute_ssh_private_key_filename"
    )

    def _compute_ssh_private_key_file(self):
        """
        If ssh private key is set in ir.config_parameter, return it as file.
        """
        for company in self:
            icp = self.env["ir.config_parameter"].sudo()
            ssh_private_key = icp.get_param("git.ssh_private_key")
            if ssh_private_key:
                company.ssh_private_key_file = ssh_private_key

    def _compute_ssh_private_key_filename(self):
        for company in self:
            company.ssh_private_key_filename = f"/tmp/company_private_key_{company.id}"
