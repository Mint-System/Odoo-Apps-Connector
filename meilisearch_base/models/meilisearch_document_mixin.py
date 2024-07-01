import json
import logging

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

    def button_view_document(self):
        return {
            "type": "ir.actions.act_window",
            "view_mode": "form",
            "res_model": self._name,
            "res_id": self.id,
            "context": {
                "create": True,
                "delete": True,
                "edit": True,
            },
        }

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
            record.index_document = json.dumps(document, indent=4)
        self._update_documents()

    def _update_documents(self):
        index = self.env["meilisearch.index"].get_matching_index(model=self[:0]._name)
        for document in self:
            document._update_document(index)

    def _update_document(self, index):
        if index:
            try:
                resp = index.update_documents([json.loads(self.index_document)])
                self.index_result = "queued"
                self.index_response = resp
                self.index_date = resp.enqueued_at
            except Exception as e:
                self.index_result = "error"
                self.index_response = e
        else:
            self.index_result = "no_index"
            self.index_response = "Index not found"

    def _get_documents(self):
        index = self.env["meilisearch.index"].get_matching_index(model=self[:0]._name)
        for document in self:
            document._get_document(index)

    def _get_document(self, index):
        if index:
            try:
                resp = index.get_document(self.id)
                fields = json.loads(self.index_document).keys()
                self.index_result = "indexed"
                self.index_response = {field: getattr(resp, field) for field in fields}
            except Exception as e:
                self.index_result = "no_document"
                self.index_response = e
        else:
            self.index_result = "no_index"
            self.index_response = "Index not found"

    def _delete_documents(self):
        index = self.env["meilisearch.index"].get_matching_index(model=self[:0]._name)
        for document in self:
            document._delete_document(index)

    def _delete_document(self, index):
        if index:
            try:
                resp = index.delete_document(self.id)
                self.index_result = "queued"
                self.index_response = resp
                self.index_date = resp.enqueued_at
            except Exception as e:
                self.index_result = "error"
                self.index_response = e
        else:
            self.index_result = "no_index"
            self.index_response = "Index not found"
