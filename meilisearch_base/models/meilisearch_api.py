import logging

import meilisearch

from odoo import _, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class MeilisearchAPI(models.Model):
    _name = "meilisearch.api"
    _description = "Meilisearch API"

    name = fields.Char(required=True)
    url = fields.Char(
        string="URL", required=True, help="Enter base URL of your Meilisearch instance"
    )
    api_key = fields.Char(string="API Key", required=True)

    def button_view_indexes(self):
        return {
            "name": "MeilisearchIndexes",
            "type": "ir.actions.act_window",
            "view_mode": "tree,form",
            "res_model": "meilisearch.index",
            "domain": [("api_id", "=", self.id)],
            "context": {"default_api_id": self.id},
        }

    def button_check_api_key(self):
        return self._get_version()

    def get_meilisearch_client(self):
        return meilisearch.Client(self.url, self.api_key)

    def _get_version(self):
        self.ensure_one()
        try:
            client = self.get_meilisearch_client()
            client.health()
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Meilisearch API Key"),
                    "message": _("The Meilisearch API key for '%s' works.", self.url),
                    "sticky": False,
                    "type": "success",
                },
            }
        except Exception as e:
            raise UserError(
                _("The Meilisearch API key for '%s' does not work: %s", self.url, e)
            )
