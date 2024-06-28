import logging

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class MeilisearchIndex(models.Model):
    _name = "meilisearch.index"
    _description = "Meilisearch Index"

    sequence = fields.Integer(default=10)
    name = fields.Char(required=True)
    api_id = fields.Many2one("meilisearch.api", required=True)
    index_name = fields.Char(required=True)
    database_filter = fields.Char(
        help="If set the index is only active on matching databases."
    )
    model_id = fields.Many2one(
        "ir.model",
        required=True,
        help="Select the model this index should be active for.",
        ondelete="cascade",
    )
    model_name = fields.Char(string="Model Name", related="model_id.model", store=True)

    def copy(self, default=None):
        self.ensure_one()
        default = default or {}
        if not default.get("name"):
            default["name"] = _("%s (copy)", self.name)
        return super().copy(default)

    @api.model
    def get_matching_index(self, record):
        index = self.search(
            [
                "&",
                ("model_name", "=", record._name),
                "|",
                ("database_filter", "=", False),
                ("database_filter", "=", self._cr.dbname),
            ],
            limit=1,
        )
        return index

    def button_view_documents(self):
        tree_view_id = self.env.ref("meilisearch_base.document_view_tree")
        form_view_id = self.env.ref("meilisearch_base.document_view_form")
        return {
            "name": "Index Documents",
            "type": "ir.actions.act_window",
            "view_mode": "tree,form",
            "views": [(tree_view_id.id, "tree"), (form_view_id.id, "form")],
            "res_model": self.model_name,
            "context": {
                "group_by": ["index_result"],
                "create": False,
                "delete": False,
                "edit": False,
            },
        }

    def button_check_index(self):
        return self._get_index()

    def button_create_index(self):
        return self._post_index()

    def button_delete_index(self):
        return self._delete_index()

    def _get_index(self):
        self.ensure_one()
        client = requests.Session()
        resp = client.get(
            url=f"{self.api_id.url}/indexes/{self.index_name}",
            headers={"Authorization": "Bearer " + self.api_id.api_key},
        )
        if resp.ok:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Meilisearch Index"),
                    "message": _(
                        "The Meilisearch index '%s' was found.", self.index_name
                    ),
                    "sticky": False,
                    "type": "success",
                },
            }
        else:
            raise UserError(
                _(
                    "Could not get Meilisearch index '%s': %s",
                    self.index_name,
                    resp.text,
                )
            )

    def _post_index(self):
        self.ensure_one()
        client = requests.Session()
        resp = client.post(
            url=f"{self.api_id.url}/indexes",
            headers={"Authorization": "Bearer " + self.api_id.api_key},
            json={"uid": self.index_name, "primaryKey": "id"},
            timeout=10,
        )
        if resp.status_code == 202:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Meilisearch Index Created"),
                    "message": _(
                        "The Meilisearch index '%s' has been created.", self.index_name
                    ),
                    "sticky": False,
                    "type": "success",
                },
            }
        else:
            raise UserError(
                _(
                    "Could not create the Meilisearch index '%s': %s",
                    self.index_name,
                    resp.text,
                )
            )

    def _delete_index(self):
        self.ensure_one()
        client = requests.Session()
        resp = client.delete(
            url=f"{self.api_id.url}/indexes/{self.index_name}",
            headers={"Authorization": "Bearer " + self.api_id.api_key},
            timeout=10,
        )
        if resp.status_code == 202:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Meilisearch Index Deleted"),
                    "message": _(
                        "The Meilisearch index '%s' has been deleted.", self.index_name
                    ),
                    "sticky": False,
                    "type": "success",
                },
            }
        else:
            raise UserError(
                _(
                    "Could not delete the Meilisearch index '%s': %s",
                    self.index_name,
                    resp.text,
                )
            )
