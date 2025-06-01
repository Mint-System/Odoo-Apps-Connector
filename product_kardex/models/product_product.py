from odoo import models


class ProductProduct(models.Model):
    _inherit = "product.product"

    def get_info_from_kardex(self):
        for product in self:
            notification = product.product_tmpl_id.get_info_from_kardex()
        return notification

    def sync_stock_of_single_product(self):
        for product in self:
            product.product_tmpl_id.sync_stock_of_single_product()
