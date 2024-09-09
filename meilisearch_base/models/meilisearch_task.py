import logging

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


class MeilisearchTask(models.Model):
    _name = "meilisearch.task"
    _description = "Meilisearch Task"

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
    document_ids = fields.One2many(
        "meilisearch.document.mixin", compute="_compute_document_ids"
    )

    def name_get(self):
        res = []
        for task in self:
            res.append(
                (task.id, _("%s - %s (%s)") % (task.name, task.index_id.model, task.uid))
            )
        return res

    def _compute_document_ids(self):
        for task in self:
            task.document_ids = self.env[task.index_id.model].search(
                [("task_id", "=", task.id)]
            )

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
        self.write({"status": "succeeded"})

    def task_failed(self):
        self.write({"status": "failed"})

    def fetch_status(self, client):
        self.ensure_one()
        index_task = client.get_task(self.uid)
        self.write({"status": index_task.status, "response": index_task})

    @api.model
    def _create_and_wait_for_completion(self, index, name, uid):
        client = index.get_client()
        index_task = client.get_task(uid)
        task = self.create(
            {
                "name": name,
                "index_id": index.id,
                "uid": uid,
                "status": index_task.status,
            }
        )

        # Loop until task is processed
        # while index_task.status in ["enqueued", "processing"]:
        #     task.fetch_status(client)
        #     time.sleep(0.25)

        # If task is finished call the hooks
        if index_task.status == "succeeded":
            task.task_succeeded()
        elif index_task.status == "failed":
            task.task_failed()

        return task
