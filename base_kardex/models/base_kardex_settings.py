from odoo import fields, models


class BaseKardexSettings(models.TransientModel):
    _name = "base.kardex.settings"
    # _inherit = 'res.config.settings'
    _description = "Base Kardex Settings"

    send_to_kardex_on_create = fields.Boolean(
        string="Send to Kardex on Create", default=False
    )
    number_of_kardex_products = fields.Integer(
        string="Number of Sync Kardex Products", default=5
    )
    kardex_date_handling = fields.Selection(
        selection=[("send", "Send"), ("create", "Create")],
        default="send",
        string="Kardex Date Handling",
    )


# SEND_KARDEX_PRODUCT_ON_CREATE=False
# NUMBER_OF_KARDEX_PRODUCTS_TO_GET = 5
# KARDEX_DATE_HANDLING = 'send' # or 'create'
