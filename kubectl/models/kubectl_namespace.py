import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class KubectlNamespace(models.Model):
    _name = "kubectl.namespace"
    _description = "Kubectl Namespace"

    name = fields.Char()
