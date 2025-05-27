from odoo import api, fields, models

class KardexTransferMixin(models.AbstractModel):
    _name = "kardex.transfer.mixin"

    def send_to_kardex(self):
        # implement Kardex transfer logic for a single move line here
        pass

