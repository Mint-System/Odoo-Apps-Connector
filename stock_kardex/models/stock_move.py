import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class StockMove(models.Model):
    _inherit = ["stock.move"]
    products_domain = fields.Binary(
        string="products domain",
        help="Dynamic domain used for the products that can be chosen on a move line",
        compute="_compute_products_domain",
    )
    # product_id = fields.Many2one(
    #     "product.product",
    #     string="Product",
    #     domain="[('kardex', '=', parent.kardex)]",
    # )  # this adds domain to existing domain!
    kardex_id = fields.Integer(string="Kardex Id")
    kardex_done = fields.Boolean(string="in Kardex bekannt", default=False)
    kardex_row_create_time = fields.Char(string="Kardex Row_Create_Time")
    kardex_row_update_time = fields.Char(string="Kardex Row_Update_Time")
    kardex_status = fields.Selection(
        selection=[("0", "Ready"), ("1", "Pending"), ("2", "Success"), ("3", "Error")],
        default="0",
        string="Kardex STATUS",
        compute="_compute_kardex_status",
        store=True,
    )
    kardex_running_id = fields.Char(string="Picking BzId")
    kardex_sync = fields.Boolean(default=False)
    kardex_journal_status = fields.Char(string="Komplett")
    has_kardex_location = fields.Boolean(compute="_compute_has_kardex_location", store=False)
    kardex_running_id_string = fields.Char(string="BzIds", compute="_compute_kardex_running_id_string", store=False)
    state = fields.Selection(selection_add=[("waiting_for_kardex", "Waiting for Kardex")])

    # tracking_type_code = fields.Char(
    #     string='Tracking Code',
    #     compute='_compute_tracking_type_code',
    #     store=False
    # )
    tracking_type_badge = fields.Html(
        string="Tracking",
        compute="_compute_tracking_type_badge",
        sanitize=False,  # Only use if you're 100% sure your HTML is safe
        store=False,
    )

    @api.depends("move_line_ids.kardex_running_id")
    def _compute_kardex_running_id_string(self):
        for move in self:
            move.kardex_running_id_string = ", ".join(
                map(str, move.move_line_ids.filtered(lambda line: line.kardex_running_id).mapped("kardex_running_id"))
            )

    @api.depends("move_line_ids.kardex_status")
    def _compute_kardex_status(self):
        for move in self:
            if move.move_line_ids and all(line.kardex_status == "2" for line in move.move_line_ids):
                move.kardex_status = "2"
            elif move.move_line_ids and any(line.kardex_status == "3" for line in move.move_line_ids):
                move.kardex_status = "3"
            else:
                move.kardex_status = "1"

    @api.onchange("move_line_ids.has_kardex_location")
    @api.depends("move_line_ids.has_kardex_location")
    def _compute_has_kardex_location(self):
        for move in self:
            move.has_kardex_location = any(move.move_line_ids.mapped("has_kardex_location"))

    @api.depends("picking_id.kardex")
    def _compute_products_domain(self):
        # if picking is kardex than product must be kardex too
        # field products_domain must be included in view
        # for obj in self:
        #     if obj.picking_id.kardex:
        #         domain = [("kardex", "=", "True")]
        #     else:
        #         domain = []

        #     obj.products_domain = domain
        for obj in self:
            obj.products_domain = []

    @api.depends("product_id")
    def _compute_tracking_type_code(self):
        for line in self:
            tracking = line.product_id.tracking
            if tracking == "serial":
                line.tracking_type_code = "S"
            elif tracking == "lot":
                line.tracking_type_code = "L"
            else:
                line.tracking_type_code = ""

    @api.depends("product_id")
    def _compute_tracking_type_badge(self):
        for line in self:
            tracking = line.product_id.tracking
            badge = ""
            if tracking == "serial":
                badge = '<span style="background-color:#007bff;color:white;padding:2px 6px;border-radius:4px;font-size:85%;">S</span>'
            elif tracking == "lot":
                badge = '<span style="background-color:#28a745;color:white;padding:2px 6px;border-radius:4px;font-size:85%;">L</span>'
            line.tracking_type_badge = badge

    def _determine_picking_type(self):
        if self.picking_type_id.kardex_picking_type == "kardex_entry":
            return "entry"
        if self.picking_type_id.kardex_picking_type == "kardex_store":
            # if self.origin and self.env["purchase.order"].search([("name", "=", self.origin)]) and self.location_id.name == ENTRANCE_LOCATION:
            return "store"
        # elif (
        #     self.origin
        #     and self.env["mrp.production"].search([("name", "=", self.origin)])
        #     and self.location_id.name == POST_PRODUCTION_LOCATION
        # ):
        elif self.picking_type_id.kardex_picking_type == "kardex_postprod":
            return "postproduction"
        # elif self.origin and self.env["mrp.production"].search([("name", "=", self.origin)]):
        elif self.picking_type_id.kardex_picking_type == "kardex_prod":
            return "production"
        # elif self.origin and self.env["sale.order"].search([("name", "=", self.origin)]):
        elif self.picking_type_id.kardex_picking_type == "kardex_get":
            return "get"

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            _logger.info("### vals in stock move create %s " % (vals,))
            location_final_id = vals.get("location_final_id")
            picking_type_id = vals.get("picking_type_id")
            picking_type = self.env["stock.picking.type"].browse(picking_type_id)

            kardex_picking_type = picking_type.kardex_picking_type
            _logger.info("### picking_type in stock move create %s " % (picking_type,))
            _logger.info("### kardex picking_type_id in stock move create %s " % (kardex_picking_type,))
            product_id = vals.get("product_id")
            if product_id:
                product = self.env["product.product"].browse(product_id)

                last_location = product.last_location_id
                _logger.info("### last_location in stock move create %s " % (last_location,))
                if last_location and kardex_picking_type == "kardex_entry":
                    # vals['location_dest_id'] = last_location.id
                    vals["location_final_id"] = last_location.id
                    # pass
                # if location_final_id and location_final_id.id != last_location:
                #     vals['location_final_id'] = location_final_id

        return super().create(vals_list)

    # @api.model_create_multi
    # def create(self, vals_list):
    #     # Ensure that the product being added has kardex=True if picking has kardex=True
    #     _logger.warning("################ STOCK MOVE CREATE ################")
    #     _logger.info("### vals_list in stock move create %s " % (vals_list,))

    #     for vals in vals_list:
    #         picking_id = vals.get("picking_id")
    #         product_id = vals.get("product_id")
    #         location_final_id = (
    #             vals.get("location_final_id")
    #             if vals.get("location_final_id")
    #             else self.env["product.template"].search([("id", "=", product_id)]).location_id
    #         )

    #         if picking_id and product_id:
    #             # Retrieve the stock.picking record, see browse docs of odoo
    #             picking = self.env["stock.picking"].browse(picking_id)
    #             # Retirve the product
    #             product = self.env["product.product"].browse(vals.get("product_id"))
    #             if product.last_location_id:
    #                 _logger.info("### product last location %s " % (product.last_location_id.name,))
    #             # if picking.kardex and not product.kardex:
    #             #     raise UserError(_("You can only add Kardex products."))

    #             if location_final_id:
    #                 picking_type_code = picking.picking_type_code
    #                 origin_type = picking._check_picking_type()

    #                 if picking_type_code == "incoming" and origin_type == "store":
    #                     # last_location_id = self._get_destination_location_for_product(product)
    #                     last_location_id = product.last_location_id
    #                     vals["location_final_id"] = last_location_id.id

    #             if picking._check_picking_type() == "postproduction":
    #                 last_location_id = product.last_location_id
    #                 # last_location_id = self._get_destination_location_for_product(product)
    #                 vals["location_final_id"] = last_location_id.id

    #     records = super().create(vals_list)

    #     already_sent = []
    #     for move in records:
    #         picking = move.picking_id
    #         parent = self.env["mrp.production"].search([("name", "=", picking.origin)])
    #         # NEU 14.5.2025 uk
    #         # if not parent:
    #         #     parent = self.env["sale.order"].search([("name", "=", picking.origin)], limit=1)
    #         # _logger.info("### parent %s" % (parent.name,))
    #         if parent and picking.picking_type_code == "internal" and picking.id not in already_sent:
    #             # picking.send_to_kardex(picking.origin)
    #             already_sent.append(picking.id)

    #     _logger.warning("################ END OF STOCK MOVE CREATE ################")

    #     return records

    # @api.model
    # def _action_confirm(self, merge=True, merge_into=False):
    #     # Call super to create stock moves and pickings
    #     _logger.info("### _action_confirm called")

    #     res = super()._action_confirm(merge, merge_into)
    #     _logger.info("### action confirm res %s " % (res,))

    #     for move in res:
    #         picking = move.picking_id
    #         parent = self.env["mrp.production"].search([("name", "=", picking.origin)])

    #         kardex_moves = picking.move_ids.filtered(lambda move: move.product_id.kardex)

    #         if (
    #             parent
    #             and picking
    #             and kardex_moves
    #             and not picking.kardex_done
    #             and not picking._check_picking_type() == "postproduction"
    #         ):
    #             _logger.info("### kardex outgoing called")
    #             # picking.send_to_kardex(picking.origin)

    #     return res

    # def _prepare_move_line_vals(self, quantity=None, reserved_quant=None):
    #     _logger.info("### _prepare_move_line_vals")

    #     vals = super()._prepare_move_line_vals(quantity, reserved_quant)

    #     _logger.info("### product %s " % (self.product_id.name,))
    #     _logger.info("### product last location %s " % (self.product_id.last_location_id.name,))
    #     if self.product_id.last_location_id:
    #         vals['location_dest_id'] = self.product_id.last_location_id.id
    #     _logger.info("### vals %s " % (vals,))
    #     return vals
