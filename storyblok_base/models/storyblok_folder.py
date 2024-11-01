import base64
import logging

import requests
from requests_toolbelt.multipart.encoder import MultipartEncoder

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .helper import get_image_file_type

_logger = logging.getLogger(__name__)


class StoryblokFolder(models.Model):
    _name = "storyblok.folder"
    _description = "Storyblok Folder"

    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=False)
    name = fields.Char(required=True)
    folder_id = fields.Integer(required=True, string="Folder ID")
    database_filter = fields.Char(help="If set the index is only active on matching databases.")
    model_id = fields.Many2one(
        "ir.model",
        required=True,
        help="Select the model this index should be active for.",
        ondelete="cascade",
    )
    model = fields.Char(string="Model Name", related="model_id.model", store=True)

    def copy(self, default=None):
        self.ensure_one()
        default = default or {}
        if not default.get("name"):
            default["name"] = _("%s (copy)", self.name)
        return super().copy(default)

    @api.model
    def get_matching_folder(self, model):
        folder = self.search(
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
        if folder:
            return folder
        else:
            return False

    def get_storyblok_settings(self):
        icp = self.env["ir.config_parameter"].sudo()
        url = icp.get_param("storyblok.api_url")
        space_id = icp.get_param("storyblok.space_id")
        api_key = icp.get_param("storyblok.api_key")

        if not url or not space_id or not api_key:
            _logger.error(_("Storyblok Url, Space ID and API key need to be configured in the system parameters."))

        return url, space_id, api_key

    def upload_asset(self, record, asset):
        self.ensure_one()

        url, space_id, api_key = self.get_storyblok_settings()

        if url and space_id and api_key:
            try:
                url = f"{url}/v1/spaces/{str(space_id)}/assets/"
                file = base64.decodebytes(asset)
                filename = f"{self.model.replace('.', '_')}-{record.id}.{get_image_file_type(file)}"
                headers = {"Authorization": api_key}
                data = {
                    "filename": filename,
                    "asset_folder_id": self.folder_id,
                }
                if record.storyblok_asset_id:
                    data["id"] = record.storyblok_asset_id
                response = requests.post(url, json=data, headers=headers, timeout=10)
                response.raise_for_status()

                signed_request = response.json()
                form = MultipartEncoder(fields={**signed_request["fields"], "file": (filename, file, "image/png")})
                response = requests.post(
                    signed_request["post_url"], data=form, headers={"Content-Type": form.content_type}, timeout=10
                )

                if response.status_code == 204:
                    record.write(
                        {
                            "document_url": "https:" + signed_request["pretty_url"],
                            "storyblok_asset_id": signed_request["id"],
                        }
                    )
                else:
                    raise UserError(_("Could not upload asset: %s", response.text))

            except Exception as e:
                raise UserError(_("Could not upload asset: %s", e)) from e

    def delete_asset(self, record):
        self.ensure_one()

        url, space_id, api_key = self.get_storyblok_settings()

        if record.storyblok_asset_id and url and space_id and api_key:
            try:
                url = f"{url}/v1/spaces/{str(space_id)}/assets/{record.storyblok_asset_id}"
                headers = {"Authorization": api_key}
                requests.delete(url, headers=headers, timeout=10)
                record.write(
                    {
                        "document_url": False,
                        "storyblok_asset_id": False,
                    }
                )
            except Exception as e:
                raise UserError(_("Could not upload asset: %s", e)) from e
