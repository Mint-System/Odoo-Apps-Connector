import logging

from odoo import api, models

_logger = logging.getLogger(__name__)


class Country(models.Model):
    _name = "res.country"
    _inherit = ["res.country", "meilisearch.document.mixin"]

    def _prepare_index_document(self):
        document = super()._prepare_index_document()
        document["code"] = self.code
        document["currency_name"] = self.currency_id.name
        return document

    def _get_index_document_filter(self):
        return lambda r: r.code == "CH"

    @api.depends("code", "currency_id.name")
    def _compute_index_document(self):
        return super()._compute_index_document()
