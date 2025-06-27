from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    kardex_test_operation = fields.Boolean(string="Test Operation", config_parameter="kardex.test.operation")
    remove_kardex_quants_not_in_ppg_shuttle = fields.Boolean(
        string="Set Kardex quant to zero if not in PPG shuttle", config_parameter="kardex.remove_quants", default=False
    )
    make_quant_sync_before_mo = fields.Boolean(
        string="Make quant sync before MO", config_parameter="kardex.make_quant_sync", default=False
    )
