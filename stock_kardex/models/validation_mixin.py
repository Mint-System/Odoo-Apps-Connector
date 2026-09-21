from odoo import _, models
from odoo.exceptions import UserError


class ValidationMixin(models.AbstractModel):
    """Refuse to confirm Kardex orders while a needed Kardex picking type is not configured."""

    _name = "validation.mixin"
    _description = "Validation Mixin"

    def validate_function(self, kardex_picking_types):
        """Check that each Kardex picking type is set on a picking type (only for Kardex orders)."""
        if not self.filtered("kardex"):
            return
        missing = [
            kardex_picking_type
            for kardex_picking_type in kardex_picking_types
            if not self.env["stock.picking.type"].search_count([("kardex_picking_type", "=", kardex_picking_type)])
        ]
        if missing:
            raise UserError(
                _(
                    "There is no picking type associated to kardex picking type = %s. "
                    "Please correct this in the configuration.",
                    ", ".join(missing),
                )
            )

    def action_confirm(self):
        if self._name == "sale.order":
            self.validate_function(["kardex_get"])
        elif self._name == "mrp.production":
            self.validate_function(["kardex_prod", "kardex_postprod"])
        return super().action_confirm()

    def button_confirm(self):
        if self._name == "purchase.order":
            self.validate_function(["kardex_store"])
        return super().button_confirm()
