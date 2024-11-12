from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    module_storyblok_base = fields.Boolean("Integrate with storyblok")
    storyblok_api_url = fields.Char(
        "Storyblok API Url", config_parameter="storyblok.api_url"
    )
    storyblok_space_id = fields.Char(
        "Storyblok Space ID", config_parameter="storyblok.space_id"
    )
    storyblok_api_key = fields.Char(
        "Storyblok API Key", config_parameter="storyblok.api_key"
    )
