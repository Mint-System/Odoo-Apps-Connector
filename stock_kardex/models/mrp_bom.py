import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class MrpBom(models.Model):
    _name = "mrp.bom"
    _inherit = ["mrp.bom"]
    _description = "Kardex BoM"

    kardex = fields.Boolean(compute="_compute_kardex", store=True)

    bom_line_count = fields.Integer(string="BoM Line Count", compute="_compute_bom_line_count", store=False)

    @api.depends("product_tmpl_id.kardex")
    def _compute_kardex(self):
        for bom in self:
            bom.kardex = bom.product_tmpl_id.kardex

    def send_to_kardex(self):
        pass

    def _compute_bom_line_count(self):
        for bom in self:
            bom.bom_line_count = len(bom.bom_line_ids)


class MrpBomLine(models.Model):
    _name = "mrp.bom.line"
    _inherit = ["mrp.bom.line"]

    product_kardex_location = fields.Char(compute="_compute_product_kardex_location", store=False)

    def _compute_product_kardex_location(self):
        for bom in self:
            product_default_code = bom.product_tmpl_id.default_code
            data_material, data = self.env["product.template"]._read_external_object_from_proddb(
                default_code=product_default_code
            )
            location_list = []
            for row in data:
                if row["LocationName"].startswith("Shuttle"):
                    location_list.append("S")
                elif row["LocationName"].startswith("Pallete"):
                    location_list.append("P")
                else:
                    location_list.append("O")

            bom.product_kardex_location = ", ".join(set(location_list))


#     # not needed
#     # TODO: delete this field
#     products_domain = fields.Binary(
#         string="products domain",
#         help="Dynamic domain used for the products that can be chosen on a move line",
#         compute="_compute_products_domain",
#     )
#     product_id = fields.Many2one(
#         "product.product",
#         string="Product",
#         domain="[('kardex', '=', parent.kardex)]",
#     )  # this adds domain to existing domain!

#     # complicated domain setting
#     # does override existing domain
#     # TODO: delete
#     @api.depends("bom_id.product_tmpl_id")
#     def _compute_products_domain(self):
#         # if picking is kardex than product must be kardex too
#         # could also be done by onchange but dynamic domain setting by onchange method seems to deprecated in odoo 17
#         # field products_domain must be included in view

#         for obj in self:
#             if obj.bom_id.product_tmpl_id:
#                 kardex_boolean = obj.bom_id.product_tmpl_id.kardex
#                 obj.products_domain = [("kardex", "=", kardex_boolean)]
#             else:
#                 # Existing domain to all products if no product template is set in BOM
#                 obj.products_domain = []
