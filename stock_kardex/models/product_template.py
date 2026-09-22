from odoo import api, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    @api.depends("categ_id.kardex", "last_location_id.kardex")
    def _compute_product_kardex(self):
        """Extends product_kardex's rule: also Kardex if the product's last location is."""
        for product in self:
            product.kardex = bool(product.categ_id.kardex or product.last_location_id.kardex)
