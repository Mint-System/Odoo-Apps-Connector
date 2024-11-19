import json
import logging
import pytz
import datetime

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class MeilsearchDocumentMixin(models.AbstractModel):
    _name = "meilisearch.document.mixin"
    _description = "Meilisearch Document Mixin"
    _batch_size = 80

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

    def documents_indexed(self, response):
        self.write({"index_result": "indexed", "index_response": response})

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

        # Filter all records that should be indexed
        index_records = self.filtered(self._get_index_document_filter())

        # Update Meilisearch document
        for record in index_records:
            document = record._prepare_index_document()
            record.index_document = json.dumps(document, indent=4)

        # Create update task
        if index:
            index_records._update_documents(index)

        # Get documents that are indexed and no longer match with filter
        delete_records = (
            self.filtered(lambda d: d.index_result == "indexed") - index_records
        )
        if delete_records:
            delete_records._delete_documents()

    def _get_batches(self, batch_size=0):
        if not batch_size:
            batch_size = self._batch_size
        for i in range(0, len(self), batch_size):
            yield self[i : i + batch_size]

    def _update_documents(self, index):
        client = index.get_client()

        for batch in self._get_batches():
            if client:
                try:
                    res = client.index(index.index_name).update_documents(
                        [json.loads(self.index_document) for self in batch]
                    )
                    task_id = False
                    if index.create_task:
                        task_id = self.env["meilisearch.task"].create(
                            {
                                "name": "documentAdditionOrUpdate",
                                "index_id": index.id,
                                "uid": res.task_uid,
                            }
                        )
                    # _logger.warning(["updated", task_id.uid])
                    batch.update(
                        {
                            "index_result": "queued",
                            "index_response": "Task enqueued",
                            "index_date": res.enqueued_at,
                            "task_id": task_id.id if task_id else False,
                        }
                    )
                    if index.create_task:
                        self.env.cr.commit()
                except Exception as e:
                    batch.write({"index_result": "error", "index_response": e})
            else:
                batch.write(
                    {"index_result": "no_index", "index_response": "Index not found"}
                )

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
                            rec.documents_indexed(json.dumps(document, indent=4))
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
                batch.write(
                    {"index_result": "no_index", "index_response": "Index not found"}
                )

    def _delete_documents(self):
        index = self.env["meilisearch.index"].get_matching_index(model=self[:0]._name)
        client = index.get_client()

        for batch in self._get_batches():
            if client:
                try:
                    search_filter = (
                        f"{' OR '.join(['id='+str(rec.id) for rec in batch])}"
                    )
                    res = client.index(index.index_name).delete_documents(
                        filter=search_filter
                    )
                    task_id = False
                    if index.create_task:
                        task_id = self.env["meilisearch.task"].create(
                            {
                                "name": "documentDeletion",
                                "index_id": index.id,
                                "uid": res.task_uid,
                            }
                        )
                    # _logger.warning(["deleted", task_id.uid])
                    batch.update(
                        {
                            "index_result": "queued",
                            "index_response": "Task enqueued",
                            "index_date": res.enqueued_at,
                            "task_id": task_id.id if task_id else False,
                        }
                    )
                    if index.create_task:
                        self.env.cr.commit()
                except Exception as e:
                    batch.write({"index_result": "error", "index_response": e})
            else:
                batch.write(
                    {"index_result": "no_index", "index_response": "Index not found"}
                )
    def _convert_to_timestamp(self, dt, tz=pytz.UTC):
        if not dt:
            return 0
        if isinstance(dt, datetime.date) and not isinstance(dt, datetime.datetime):
            dt = datetime.datetime.combine(dt, datetime.datetime.min.time())
        if tz:
            dt = dt.astimezone(tz)
        return int(dt.timestamp())