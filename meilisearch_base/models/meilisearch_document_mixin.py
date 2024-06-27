import json
import logging
from datetime import datetime

import requests

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class MeilsearchDocumentMixin(models.AbstractModel):
    _name = "meilisearch.document.mixin"
    _description = "Meilisearch Document Mixin"

    name = fields.Char()
    index_date = fields.Datetime()
    index_document = fields.Text(compute="_compute_index_document", store=True)
    index_result = fields.Selection(
        [
            ("queued", "Queued"),
            ("indexed", "Indexed"),
            ("error", "Error"),
            ("no_document", "No Document"),
            ("no_index", "No Index"),
        ]
    )
    index_response = fields.Text()

    def update_index_document(self):
        return self._compute_index_document()

    def check_index_document(self):
        return self._get_documents()

    def delete_index_document(self):
        return self._delete_documents()

    def unlink(self):
        self._delete_documents()
        return super().unlink()

    def _prepare_index_document(self):
        self.ensure_one()
        return {"id": self.id, "name": self.name}

    @api.depends("name")
    def _compute_index_document(self):
        for record in self:
            document = record._prepare_index_document()
            record.index_document = json.dumps([document], indent=4)
        self._post_documents()

    def _post_documents(self):
        index = self.env["meilisearch.index"].get_matching_index(self[:0])
        client = requests.Session()
        for document in self:
            if index:
                resp = client.post(
                    url=f"{index.api_id.url}/indexes/{index.index_name}/documents",
                    headers={
                        "Authorization": "Bearer " + index.api_id.api_key,
                        "Content-type": "application/json",
                    },
                    timeout=10,
                    json=document._prepare_index_document(),
                )

                if resp.status_code == 202:
                    document.index_result = "queued"
                    document.index_response = resp.text
                    enqued_date = json.loads(resp.text)["enqueuedAt"].split(".")[0]
                    document.index_date = datetime.strptime(
                        enqued_date, "%Y-%m-%dT%H:%M:%S"
                    )
                else:
                    document.index_result = "error"
                    document.index_response = resp.text
            else:
                document.index_result = "no_index"
                document.index_response = "Index not found"

    def _get_documents(self):
        index = self.env["meilisearch.index"].get_matching_index(self[:0])
        client = requests.Session()
        for document in self:
            if index:
                resp = client.get(
                    url=f"{index.api_id.url}/indexes/{index.index_name}/documents/{document.id}",
                    headers={
                        "Authorization": "Bearer " + index.api_id.api_key,
                    },
                    timeout=10,
                )

                if resp.ok:
                    document.index_result = "indexed"
                    document.index_response = resp.text
                else:
                    document.index_result = "no_document"
                    document.index_response = resp.text
            else:
                document.index_result = "no_index"
                document.index_response = "Index not found"

    def _delete_documents(self):
        index = self.env["meilisearch.index"].get_matching_index(self[:0])
        client = requests.Session()
        for document in self:
            if index:
                resp = client.delete(
                    url=f"{index.api_id.url}/indexes/{index.index_name}/documents/{document.id}",
                    headers={
                        "Authorization": "Bearer " + index.api_id.api_key,
                    },
                    timeout=10,
                )

                if resp.status_code == 202:
                    document.index_result = "queued"
                    document.index_response = resp.text
                    enqued_date = json.loads(resp.text)["enqueuedAt"].split(".")[0]
                    document.index_date = datetime.strptime(
                        enqued_date, "%Y-%m-%dT%H:%M:%S"
                    )
                else:
                    document.index_result = "error"
                    document.index_response = resp.text
            else:
                document.index_result = "no_index"
                document.index_response = "Index not found"

