from odoo import models, fields

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    kardex_test_operation = fields.Boolean(
        string="Test Operation",
        config_parameter='kardex.test.operation'
    )
