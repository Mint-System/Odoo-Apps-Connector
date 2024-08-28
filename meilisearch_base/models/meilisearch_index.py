import json
import logging

import meilisearch

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class MeilisearchIndex(models.Model):
    _name = "meilisearch.index"
    _description = "Meilisearch Index"

    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    name = fields.Char(required=True)
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
    model = fields.Char(string="Model Name", related="model_id.model", store=True)
    index_settings = fields.Text(
        required=True,
        default="""{
    "filterableAttributes": [
        "id"
    ]
}""",
    )

    def copy(self, default=None):
        self.ensure_one()
        default = default or {}
        if not default.get("name"):
            default["name"] = _("%s (copy)", self.name)
        return super().copy(default)

    def get_meilisearch_client(self):
        icp = self.env["ir.config_parameter"].sudo()
        return meilisearch.Client(
            url=icp.get_param("meilisearch.api_url"),
            api_key=icp.get_param("meilisearch.api_key"),
            timeout=10,
        )

    @api.model
    def get_matching_index(self, model):
        index = self.search(
            [
                "&",
                ("active", "=", True),
                ("model", "=", model),
                "|",
                ("database_filter", "=", False),
                ("database_filter", "=", self._cr.dbname),
            ],
            limit=1,
        )
        if index:
            return index.get_meilisearch_client().index(index.index_name)
        else:
            return False

    def button_view_documents(self):
        tree_view_id = self.env.ref("meilisearch_base.document_view_tree")
        form_view_id = self.env.ref("meilisearch_base.document_view_form")
        search_view_id = self.env.ref("meilisearch_base.document_view_search")
        return {
            "name": "Index Documents",
            "type": "ir.actions.act_window",
            "view_mode": "tree,form",
            "views": [(tree_view_id.id, "tree"), (form_view_id.id, "form")],
            "res_model": self.model,
            "context": {
                "search_default_group_by_index_result": True,
                "create": False,
                "delete": False,
                "edit": False,
            },
            "search_view_id": [search_view_id.id, "search"],
        }

    def button_check_index(self):
        return self._get_index()

    def button_create_index(self):
        return self._create_index()

    def button_update_index(self):
        return self._update_index()

    def button_delete_index(self):
        return self._delete_index()

    def button_check_api_key(self):
        return self._get_version()

    def _get_version(self):
        self.ensure_one()
        try:
            url = (
                self.env["ir.config_parameter"].sudo().get_param("meilisearch.api_url"),
            )
            client = self.get_meilisearch_client()
            client.health()
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Meilisearch API Key"),
                    "message": _("The Meilisearch API key for '%s' works.", url),
                    "sticky": False,
                    "type": "success",
                },
            }
        except Exception as e:
            raise UserError(
                _("The Meilisearch API key for '%s' does not work: %s", url, e)
            ) from None

    def _get_index(self):
        self.ensure_one()
        try:
            self.get_meilisearch_client().get_index(self.index_name)
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
        except Exception as e:
            raise UserError(
                _(
                    "Could not get Meilisearch index '%s': %s",
                    self.index_name,
                    e,
                )
            ) from None

    def _create_index(self):
        self.ensure_one()
        try:
            self.get_meilisearch_client().create_index(
                self.index_name, {"primaryKey": "id"}
            )
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
        except Exception as e:
            raise UserError(
                _(
                    "Could not create the Meilisearch index '%s': %s",
                    self.index_name,
                    e.message,
                )
            ) from None

    def _update_index(self):
        self.ensure_one()
        try:
            self.get_meilisearch_client().index(self.index_name).update_settings(
                json.loads(self.index_settings)
            )
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Meilisearch Index Created"),
                    "message": _(
                        "The Meilisearch index settings updated for '%s'.",
                        self.index_name,
                    ),
                    "sticky": False,
                    "type": "success",
                },
            }
        except Exception as e:
            raise UserError(
                _(
                    "Could not create the Meilisearch index '%s': %s",
                    self.index_name,
                    e.message,
                )
            ) from None

    def _delete_index(self):
        self.ensure_one()
        try:
            self.get_meilisearch_client().delete_index(self.index_name)
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Meilisearch Index Deleted"),
                    "message": _(
                        "The Meilisearch index '%s' was deleted.", self.index_name
                    ),
                    "sticky": False,
                    "type": "success",
                },
            }
        except Exception as e:
            raise UserError(
                _(
                    "Could not delete the Meilisearch index '%s': %s",
                    self.index_name,
                    e.message,
                )
            ) from None
