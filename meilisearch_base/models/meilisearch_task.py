import logging

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


class MeilisearchTask(models.Model):
    _name = "meilisearch.task"
    _description = "Meilisearch Task"
    _order = "uid desc"

    name = fields.Char(required=True)
    uid = fields.Integer("UID", required=True)
    status = fields.Selection(
        [
            ("enqueued", "Enqued"),
            ("processing", "Processing"),
            ("succeeded", "Succeeded"),
            ("failed", "Failed"),
        ],
        default="enqueued",
        required=True,
    )
    response = fields.Text()
    index_id = fields.Many2one("meilisearch.index", required=True)

    def name_get(self):
        res = []
        for task in self:
            res.append(
                (
                    task.id,
                    _("%s - %s (%s)") % (task.name, task.index_id.model, task.uid),
                )
            )
        return res

    def _get_document_ids(self):
        self.ensure_one()
        document_ids = self.env[self.index_id.model].search([("task_id", "=", self.id)])
        return document_ids

    def button_check_task(self):
        self.ensure_one()
        client = self.index_id.get_client()
        self.fetch_status(client)

    def button_view_documents(self):
        tree_view_id = self.env.ref("meilisearch_base.document_view_tree")
        form_view_id = self.env.ref("meilisearch_base.document_view_form")
        search_view_id = self.env.ref("meilisearch_base.document_view_search")
        return {
            "name": "Index Documents",
            "type": "ir.actions.act_window",
            "view_mode": "tree,form",
            "views": [(tree_view_id.id, "tree"), (form_view_id.id, "form")],
            "res_model": self.index_id.model,
            "context": {
                "search_default_group_by_index_result": True,
                "create": False,
                "delete": False,
                "edit": False,
            },
            "search_view_id": [search_view_id.id, "search"],
            "domain": [("task_id", "=", self.id)],
        }

    def task_succeeded(self):
        self.ensure_one()
        self.write(
            {
                "status": "succeeded",
                "response": "Task succeeded",
            }
        )
        if self.name == "documentAdditionOrUpdate":
            document_ids = self._get_document_ids()
            document_ids.documents_indexed("Task succeeded")

    def task_failed(self):
        self.ensure_one()
        self.write(
            {
                "status": "failed",
                "response": "Task failed",
            }
        )
        documents = self._get_document_ids()
        documents.write({"index_result": "error", "index_response": "Task failed"})

    def fetch_status(self, client):
        self.ensure_one()
        index_task = client.get_task(self.uid)
        self.write({"status": index_task.status, "response": index_task})

    @api.autovacuum
    def _gc_meilisearch_tasks(self):
        for task in self.search([]):
            document = self.env[task.index_id.model].search(
                [("task_id", "=", task.id)], limit=1
            )
            if not document:
                task.unlink()
