import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class Partner(models.Model):
    _name = "res.partner"
    _inherit = ["res.partner", "storyblok.asset.mixin"]

    image_1920 = fields.Image(inverse="_inverse_image_1920")

    def _inverse_image_1920(self):
        self.upload_asset(self.image_1920)
