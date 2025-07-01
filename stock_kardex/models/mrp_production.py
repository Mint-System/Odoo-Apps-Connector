import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class MrpProduction(models.Model):
    _name = "mrp.production"
    _inherit = ["validation.mixin", "mrp.production"]
    _description = "Kardex MRP Production"

    kardex = fields.Boolean(compute="_compute_kardex", store=True)

    @api.depends("product_id.product_tmpl_id.kardex")
    def _compute_kardex(self):
        for record in self:
            # Check if the related product template's kardex field is True
            record.kardex = record.product_id.product_tmpl_id.kardex

    @api.model
    def create(self, vals_list):
        param = self.env["ir.config_parameter"].sudo()

        sync_before_mo = param.get_param("kardex.make_quant_sync") == "True"
        records = super().create(vals_list)

        for production in records:
            bom = production.bom_id
            if bom and sync_before_mo:
                for line in bom.bom_line_ids:
                    product_tmpl = line.product_id.product_tmpl_id
                    if hasattr(product_tmpl, "sync_stock_of_single_product"):
                        product_tmpl.sync_stock_of_single_product()

        return records
