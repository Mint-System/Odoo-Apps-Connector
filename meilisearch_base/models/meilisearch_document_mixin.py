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
            ("not_found", "Not Found"),
            ("no_index", "No Index"),
        ]
    )
    index_response = fields.Text()
    task_id = fields.Many2one("meilisearch.task")

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

    def check_index_document(self):
        return self._get_documents()

    def update_index_document(self):
        return self._compute_index_document()

    def delete_index_document(self):
        return self._delete_documents()

    def unlink(self):
        self._delete_documents()
        return super().unlink()

    def _prepare_index_document(self):
        self.ensure_one()
        return {"id": self.id, "name": self.name}

    def _get_index_document_filter(self):
        return lambda r: True

    @api.depends("name")
    def _compute_index_document(self):
        index = self.env["meilisearch.index"].get_matching_index(model=self[:0]._name)
        records = self.filtered(self._get_index_document_filter())
        for record in records:
            document = record._prepare_index_document()
            record.index_document = json.dumps(document, indent=4)
        if index:
            records._update_documents(index)

    def _get_batches(self, batch_size):
        for i in range(0, len(self), batch_size):
            yield self[i : i + batch_size]

    def _update_documents(self, index):
        client = index.get_client()

        for batch in self._get_batches(80):
            if client:
                try:
                    res = client.index(index.index_name).update_documents(
                        [json.loads(self.index_document) for self in batch]
                    )
                    batch.index_result = "queued"
                    batch.index_response = res
                    batch.index_date = res.enqueued_at
                    batch.task_id = self.env[
                        "meilisearch.task"
                    ]._create_and_wait_for_completion(
                        index, "update_documents", res.task_uid
                    )
                except Exception as e:
                    batch.index_result = "error"
                    batch.index_response = e
            else:
                batch.index_result = "no_index"
                batch.index_response = "Index not found"

    def _get_documents(self):
        index = self.env["meilisearch.index"].get_matching_index(model=self[:0]._name)
        client = index.get_client()

        # Batch size has to match the max operators in the filter
        for batch in self._get_batches(20):
            if client:
                try:
                    search_filter = (
                        f"{' OR '.join(['id='+str(rec.id) for rec in batch])}"
                    )
                    res = client.index(index.index_name).search(
                        "", {"filter": search_filter}
                    )
                    if res["hits"]:
                        found_ids = []
                        for document in res["hits"]:
                            rec = self.browse(int(document["id"]))
                            rec.index_result = "indexed"
                            rec.index_response = json.dumps(document, indent=4)
                            found_ids.append(rec.id)

                        # Update records not in hits set
                        not_found = batch.filtered(lambda r: r.id not in found_ids)
                        not_found.index_result = "not_found"
                        not_found.index_response = "Document not found"
                    else:
                        batch.index_result = "not_found"
                        batch.index_response = res
                except Exception as e:
                    batch.index_result = "error"
                    batch.index_response = e
            else:
                batch.index_result = "no_index"
                batch.index_response = "Index not found"

    def _delete_documents(self):
        index = self.env["meilisearch.index"].get_matching_index(model=self[:0]._name)
        client = index.get_client()

        for batch in self._get_batches(80):
            if client:
                try:
                    search_filter = (
                        f"{' OR '.join(['id='+str(rec.id) for rec in batch])}"
                    )
                    res = client.index(index.index_name).delete_documents(
                        filter=search_filter
                    )
                    batch.index_result = "queued"
                    batch.index_response = res
                    batch.index_date = res.enqueued_at
                    batch.task_id = self.env[
                        "meilisearch.task"
                    ]._create_and_wait_for_completion(
                        index, "delete_documents", res.task_uid
                    )
                except Exception as e:
                    batch.index_result = "error"
                    batch.index_response = e
            else:
                batch.index_result = "no_index"
                batch.index_response = "Index not found"
