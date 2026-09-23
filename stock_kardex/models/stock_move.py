import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

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
        """Default the final location of Kardex entry/store moves.

        Entry: goods return to where the product was last stored. Store: a Kardex
        product (by category or last location, see product.kardex) is by default
        routed into the Kardex location; an explicit location_final_id in vals is
        never overridden.
        """
        for vals in vals_list:
            if not vals.get("product_id"):
                continue
            picking_type = self.env["stock.picking.type"].browse(vals.get("picking_type_id"))
            product = self.env["product.product"].browse(vals["product_id"])
            if picking_type.kardex_picking_type == "kardex_entry" and product.last_location_id:
                vals["location_final_id"] = product.last_location_id.id
            elif (
                picking_type.kardex_picking_type == "kardex_store"
                and product.kardex
                and not vals.get("location_final_id")
            ):
                kardex_location = self.env["stock.location"].search([("kardex", "=", True)], limit=1)
                if kardex_location:
                    vals["location_final_id"] = kardex_location.id

        return super().create(vals_list)

    def write(self, vals):
        """Changing where a move ultimately goes can start or must not touch a Kardex send.

        A not-yet-sent line is (re-)evaluated for send_to_kardex() when location_final_id
        changes - this is what lets a picker override the computed default by hand. Once a
        line has been sent, its move's location_final_id is frozen: Kardex has already been
        told where the stock is going, and quantity/lot/status are still updated by the sync
        (they are untouched here).
        """
        changed_moves = self.env["stock.move"]
        if "location_final_id" in vals:
            changed_moves = self.filtered(lambda move: move.location_final_id.id != vals["location_final_id"])
            if changed_moves.move_line_ids.filtered("kardex_done"):
                raise UserError(_("The final location of an already sent Kardex line cannot be changed."))

        res = super().write(vals)

        for line in changed_moves.move_line_ids.filtered(lambda line: not line.kardex_done):
            line.send_to_kardex()
        return res
