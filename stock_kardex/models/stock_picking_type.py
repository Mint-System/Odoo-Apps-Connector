from odoo import api, fields, models


class StockPickingType(models.Model):
    _name = "stock.picking.type"
    _inherit = "stock.picking.type"

    kardex_picking_type = fields.Selection(
        [
            ("kardex_entry", "Kardex Entry"),
            ("kardex_store", "Kardex Store"),
            ("kardex_get", "Kardex Get"),
            ("kardex_prod", "Kardex Prod"),
            ("kardex_postprod", "Kardex Post Production"),
        ],
        string="Kardex Picking Type",
    )

    _sql_constraints = [
        ("kardex_picking_type_unique", "unique(kardex_picking_type)", "Kardex picking type must be unique"),
    ]

    @api.constrains("kardex_picking_type")
    def _check_kardex_picking_type(self):
        for record in self:
            if record.kardex_picking_type:
                existing_records = self.search(
                    [("kardex_picking_type", "=", record.kardex_picking_type), ("id", "!=", record.id)]
                )
                if existing_records:
                    raise ValidationError("This Kardex picking type is already in use")
