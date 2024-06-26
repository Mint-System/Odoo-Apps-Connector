import logging

from odoo import models

_logger = logging.getLogger(__name__)


class Country(models.Model):
    _name = "res.country"
    _inherit = ["res.country", "meilisearch.document.mixin"]

    def _prepare_index_document(self):
        document = super()._prepare_index_document()
        document["code"] = self.code
        return document
