import datetime
import json
import logging
from hashlib import sha256

import pytz

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class MeilsearchDocumentMixin(models.AbstractModel):
    _name = "meilisearch.document.mixin"
    _description = "Meilisearch Document Mixin"

    name = fields.Char()
    index_date = fields.Datetime()
    index_document = fields.Json(
        compute="_compute_index_document",
        store=True,
        help="Stores the document as JSONB.",
    )
    index_document_hash = fields.Text(compute="_compute_index_document", store=True)
    index_document_read = fields.Text(compute="_compute_index_document_read", help="Returns the document as JSON.")
    index_result = fields.Selection(
        [
            ("queued", "Queued"),
            ("indexed", "Indexed"),
            ("error", "Error"),
            ("not_found", "Not Found"),
            ("no_index", "No Index"),
        ]
    )
    index_response = fields.Text(help="Response from Meilisearch index.")

    # Compute methods

    @api.depends("name")
    def _compute_index_document(self):
        index = self.env["meilisearch.index"].get_matching_index(model=self[:0]._name)

        # Filter all records that should be indexed
        index_records = self.filtered(self._get_index_document_filter())

        # Update Meilisearch document if hash has changed
        update_records = index_records
        for record in index_records:
            document = record._prepare_index_document()
            document_hash = sha256(json.dumps(document).encode()).hexdigest()
            if (document_hash != record.index_document_hash) or record.index_result != "indexed":
                record.index_document = document
                record.index_document_hash = document_hash
            else:
                update_records = update_records - record

        # Update
        if index:
            update_records._update_documents(index)

        # Get documents that are indexed and no longer match the filter
        delete_records = self.filtered(lambda d: d.index_result == "indexed") - index_records

        # Delete these documents from index
        if delete_records:
            delete_records._delete_documents()

    def _compute_index_document_read(self):
        for record in self:
            record.index_document_read = json.dumps(record.index_document, indent=4)

    # Helper methods

    def _convert_to_timestamp(self, dt, tz=pytz.UTC):
        if not dt:
            return 0
        if isinstance(dt, datetime.date) and not isinstance(dt, datetime.datetime):
            dt = datetime.datetime.combine(dt, datetime.datetime.min.time())
        if tz:
            dt = dt.astimezone(tz)
        return int(dt.timestamp())

    # Model methods

    def check_index_document(self):
        return self._get_documents()

    def update_index_document(self):
        return self._compute_index_document()

    def delete_index_document(self):
        return self._delete_documents()

    def unlink(self):
        self._delete_documents()
        return super().unlink()

    # Action methods

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

    # Private methods

    def _prepare_index_document(self):
        self.ensure_one()
        return {"id": self.id, "name": self.name}

    def _get_index_document_filter(self):
        return lambda r: True

    def _update_documents(self, index):
        client = index.get_client()
        for offset in range(0, len(self), 20):
            batch = self[offset : offset + 20]
            if client:
                try:
                    with self.env.cr.savepoint():
                        res = client.index(index.index_name).update_documents([self.index_document for self in batch])
                        if index.create_task:
                            self.env["meilisearch.task"].create(
                                {
                                    "name": "documentAdditionOrUpdate",
                                    "index_id": index.id,
                                    "uid": res.task_uid,
                                    "document_ids": [rec.id for rec in batch],
                                }
                            )
                        batch.update(
                            {
                                "index_result": "queued",
                                "index_response": "Task enqueued",
                                "index_date": res.enqueued_at,
                            }
                        )
                except Exception as e:
                    batch.write({"index_result": "error", "index_response": e})
            else:
                batch.write({"index_result": "no_index", "index_response": "Index not found"})

    def _get_documents(self):
        index = self.env["meilisearch.index"].get_matching_index(model=self[:0]._name)
        client = index.get_client()

        # Batch size has to match the max operators in the filter
        for offset in range(0, len(self), 20):
            batch = self[offset : offset + 20]
            if client:
                try:
                    with self.env.cr.savepoint():
                        search_filter = f"{' OR '.join(['id='+str(rec.id) for rec in batch])}"
                        res = client.index(index.index_name).search("", {"filter": search_filter})
                        if res["hits"]:
                            found_ids = []
                            for document in res["hits"]:
                                rec = self.browse(int(document["id"]))
                                rec.write(
                                    {
                                        "index_result": "indexed",
                                        "index_response": json.dumps(document, indent=4),
                                    }
                                )
                                found_ids.append(rec.id)

                            # Update records not in hits set
                            not_found = batch.filtered(lambda r: r.id not in found_ids)
                            not_found.write(
                                {
                                    "index_result": "not_found",
                                    "index_response": "Document not found",
                                }
                            )
                        else:
                            batch.update(
                                {
                                    "index_result": "not_found",
                                    "index_response": res,
                                }
                            )
                except Exception as e:
                    batch.write({"index_result": "error", "index_response": e})
            else:
                batch.write({"index_result": "no_index", "index_response": "Index not found"})

    def _delete_documents(self):
        index = self.env["meilisearch.index"].get_matching_index(model=self[:0]._name)
        client = index.get_client()

        for offset in range(0, len(self), 20):
            batch = self[offset : offset + 20]
            if client:
                try:
                    with self.env.cr.savepoint():
                        search_filter = f"{' OR '.join(['id='+str(rec.id) for rec in batch])}"
                        res = client.index(index.index_name).delete_documents(filter=search_filter)
                        if index.create_task:
                            self.env["meilisearch.task"].create(
                                {
                                    "name": "documentDeletion",
                                    "index_id": index.id,
                                    "uid": res.task_uid,
                                    "document_ids": [rec.id for rec in batch],
                                }
                            )
                        batch.update(
                            {
                                "index_result": "queued",
                                "index_response": "Task enqueued",
                                "index_date": res.enqueued_at,
                                "index_document_hash": "",
                            }
                        )
                except Exception as e:
                    batch.write({"index_result": "error", "index_response": e})
            else:
                batch.write({"index_result": "no_index", "index_response": "Index not found"})
