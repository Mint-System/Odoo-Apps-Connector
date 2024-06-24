import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class MeilisearchIndex(models.Model):
    _name = "meilisearch.index"
    _inherit = "meilisearch.document.mixin"
    _description = "Meilisearch Index"

    name = fields.Char()
    index_name = fields.Char()
