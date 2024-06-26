import logging

import requests

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
        }

    def button_check_api_key(self):
        return self._get_indexes()

    def _get_indexes(self):
        self.ensure_one()
        client = requests.Session()
        resp = client.get(
            url=self.url + "/indexes",
            headers={"Authorization": "Bearer " + self.api_key},
        )
        if resp.ok:
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
        else:
            raise UserError(
                _("The Meilisearch API key for '%s' does not work.", self.url)
            )
