from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    kardex_test_operation = fields.Boolean(string="Test Operation", config_parameter="kardex.test.operation")
    remove_kardex_quants_not_in_ppg_shuttle = fields.Boolean(
        string="Remove Kardex Quants Missing in Kardex", config_parameter="kardex.remove_quants", default=False
    )
    make_quant_sync_before_mo = fields.Boolean(
        string="Sync Stock Before Manufacturing Order", config_parameter="kardex.make_quant_sync", default=False
    )
    inventory_reconciliation = fields.Selection(
        string="Inventory Reconciliation Method",
        selection=[
            ("direct", "Direct from ProdDB"),
            ("ppg", "Using PPG_Bestandsabgleich"),
        ],
        config_parameter="kardex.inv_method",
        required=True,
        default="ppg",
    )
    kardex_aggregate_palettes = fields.Boolean(
        string="Aggregate Palettes", config_parameter="kardex.aggregate_palettes", default=False
    )
