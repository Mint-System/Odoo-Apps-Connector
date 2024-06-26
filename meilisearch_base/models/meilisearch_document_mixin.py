import json
import logging

import requests

from odoo import api, fields, models

from datetime import datetime

_logger = logging.getLogger(__name__)


class MeilsearchDocumentMixin(models.AbstractModel):
    _name = "meilisearch.document.mixin"
    _description = "Meilisearch Document Mixin"

    index_date = fields.Datetime()
    index_document = fields.Text(compute="_compute_index_document", store=True)
    index_result = fields.Selection(
        [("success", "Success"), ("error", "Error"), ("no_index", "No Index")]
    )
    index_response = fields.Text()

    def _prepare_index_document(self):
        return {"id": self.id, "name": self.name}

    def update_index_document(self):
        self._compute_index_document()

    @api.depends("name")
    def _compute_index_document(self):
        index = self.env["meilisearch.index"].get_matching_index(self[:0])
        for record in self:
            document = record._prepare_index_document()
            record.index_document = json.dumps([document])
            record._post_document(index, document)

    def _post_document(self, index, document):
        self.ensure_one()
        if index:
            client = requests.Session()
            resp = client.post(
                url=index.api_id.url + "/indexes/" + index.index_name + "/documents",
                headers={
                    "Authorization": "Bearer " + index.api_id.api_key,
                    "Content-type": "application/json",
                },
                json=document,
            )

            if resp.status_code == 202:
                self.index_result = "success"
                self.index_response = resp.text
                enqued_date = json.loads(resp.text)["enqueuedAt"].split(".")[0]
                self.index_date = datetime.strptime(enqued_date, "%Y-%m-%dT%H:%M:%S")
            else:
                self.index_result = "error"
                self.index_response = resp.text
        else:
            self.index_result = "no_index"
            self.index_response = "Index not found"