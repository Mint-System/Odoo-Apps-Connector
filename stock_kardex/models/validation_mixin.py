import logging

from odoo import _, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class ValidationMixin(models.AbstractModel):
    _name = "validation.mixin"
    _description = "Validation Mixin"

    def validate_function(self, kardex_picking_types):
        for record in self:
            # check if picking types with kardex_picking_type = kardex_prod exist
            error_message = []
            for kardex_picking_type in kardex_picking_types:
                picking_type = self.env["stock.picking.type"].search(
                    [("kardex_picking_type", "=", kardex_picking_type)]
                )

                if not picking_type:
                    error_message.append(
                        _(
                            f"There is no picking type associated to kardex picking type = {kardex_picking_type}. Please correct this in the configuration."
                        )
                    )

            if len(error_message) > 0:
                raise UserError(" | ".join(error_message))

    def action_confirm(self):
        if self._name == "sale.order":
            self.validate_function(["kardex_get"])
        elif self._name == "mrp.production":
            self.validate_function(["kardex_prod", "kardex_postprod"])

        # If validation passes, continue with standard confirmation
        return super().action_confirm()

    def button_confirm(self):
        if self._name == "purchase.order":
            self.validate_function(["kardex_store"])

        # If validation passes, continue with standard confirmation
        return super().button_confirm()
