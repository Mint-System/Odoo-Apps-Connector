from odoo import api, fields, models
from odoo.exceptions import ValidationError


class StockPickingType(models.Model):
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

    kardex_direction = fields.Integer(compute="_compute_kardex_direction")

    _sql_constraints = [
        ("kardex_picking_type_unique", "unique(kardex_picking_type)", "Kardex picking type must be unique"),
    ]

    @api.depends("kardex_picking_type")
    def _compute_kardex_direction(self):
        KARDEX_DIRECTION_PICKER = {
            "kardex_entry": 0,
            "kardex_store": 3,
            "kardex_get": 4,
            "kardex_prod": 4,
            "kardex_postprod": 3,
        }
        for pc_type in self:
            pc_type.kardex_direction = KARDEX_DIRECTION_PICKER.get(pc_type.kardex_picking_type, False)

    @api.constrains("kardex_picking_type")
    def _check_kardex_picking_type(self):
        for record in self:
            if record.kardex_picking_type:
                existing_records = self.search(
                    [("kardex_picking_type", "=", record.kardex_picking_type), ("id", "!=", record.id)]
                )
                if existing_records:
                    raise ValidationError("This Kardex picking type is already in use")
