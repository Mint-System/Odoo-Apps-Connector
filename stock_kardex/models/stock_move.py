import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class StockMove(models.Model):
    _inherit = "stock.move"
    products_domain = fields.Binary(
        string="products domain",
        help="Dynamic domain used for the products that can be chosen on a move line",
        compute="_compute_products_domain",
    )
    kardex_id = fields.Integer(string="Kardex Id")
    kardex_done = fields.Boolean(related="picking_id.kardex_done", store=True)
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

    @api.depends("move_line_ids.kardex_running_id")
    def _compute_kardex_running_id_string(self):
        for move in self:
            move.kardex_running_id_string = ", ".join(
                map(
                    str,
                    move.move_line_ids.filtered(lambda line: line.kardex_running_id).mapped("kardex_running_id"),
                )
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
        for obj in self:
            obj.products_domain = []

    @api.model_create_multi
    def create(self, vals_list):
        """Moves of the Kardex entry picking type end where the product was last stored."""
        for vals in vals_list:
            picking_type = self.env["stock.picking.type"].browse(vals.get("picking_type_id"))
            if vals.get("product_id") and picking_type.kardex_picking_type == "kardex_entry":
                last_location = self.env["product.product"].browse(vals["product_id"]).last_location_id
                if last_location:
                    vals["location_final_id"] = last_location.id

        return super().create(vals_list)
