import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class KubectlCluster(models.Model):
    _name = "kubectl.cluster"
    _description = "Kubectl Cluster"

    name = fields.Char()
    server = fields.Char()
