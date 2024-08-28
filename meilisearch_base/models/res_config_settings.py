from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    module_meilisearch_base = fields.Boolean("Integrate with Meilisearch")
    meilisearch_api_url = fields.Char(
        "Meilisearch API Url", config_parameter="meilisearch.api_url"
    )
    meilisearch_api_key = fields.Char(
        "Meilisearch API Key", config_parameter="meilisearch.api_key"
    )
