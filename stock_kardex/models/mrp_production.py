import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class MrpProduction(models.Model):
    _inherit = ["mrp.production"]
    _description = "Kardex MRP Production"

    kardex = fields.Boolean(compute="_compute_kardex", store=True)

    @api.depends("product_id.product_tmpl_id.kardex")
    def _compute_kardex(self):
        for record in self:
            # Check if the related product template's kardex field is True
            record.kardex = record.product_id.product_tmpl_id.kardex

    def action_confirm(self):
        for production in self:
            # check if picking types with kardex_picking_type = kardex_prod exist
            prod_picking_type = self.env["stock.picking.type"].search([("kardex_picking_type", "=", "kardex_prod")])
            postprod_picking_type = self.env["stock.picking.type"].search(
                [("kardex_picking_type", "=", "kardex_postprod")]
            )

            error_message = []
            if not prod_picking_type:
                error_message.append(
                    _(
                        "There is no picking type associated to kardex picking type = kardex_prod. Please correct this in the configuration."
                    )
                )
            if not postprod_picking_type:
                error_message.append(
                    _(
                        "There is no picking type associated to kardex picking type = kardex_postprod. Please correct this in the configuration."
                    )
                )
            if len(error_message) > 0:
                raise UserError(" | ".join(error_message))

        # If validation passes, continue with standard confirmation
        return super().action_confirm()
