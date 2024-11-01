import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class StoryblokAssetMixin(models.AbstractModel):
    _name = "storyblok.asset.mixin"
    _description = "Storyblok Asset Mixin"

    document_url = fields.Char()
    storyblok_asset_id = fields.Integer()

    def upload_asset(self, asset):
        if self.env.context.get("storyblok_upload", True):
            folder = self.env["storyblok.folder"].get_matching_folder(self._name)
            if folder:
                for rec in self:
                    if asset:
                        folder.upload_asset(rec, asset)
                    if not asset:
                        folder.delete_asset(rec)
