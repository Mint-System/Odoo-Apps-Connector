import logging

from odoo import api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

from .config import (
    CREATE_SERIAL_FOR_PRODUCTION,
    CREATE_SERIAL_FOR_STORE,
    KARDEX_DESTINATION,
    OVERRIDE_SERIAL_FOR_PRODUCTION,
    OVERRIDE_SERIAL_FOR_STORE,
    POST_PRODUCTION_LOCATION,
)
from .helper import _get_sql_for_journal_query


class StockPicking(models.Model):
    _name = "stock.picking"
    _inherit = ["stock.picking", "base.kardex.mixin"]
    _description = "Stock Kardex Picking"

    kardex = fields.Boolean(default=False, compute="_compute_kardex", store=True)
    kardex_id = fields.Integer()
    kardex_done = fields.Boolean(string="in Kardex bekannt", default=False)
    kardex_row_create_time = fields.Char(string="Kardex Row_Create_Time")
    kardex_row_update_time = fields.Char(string="Kardex Row_Update_Time")
    kardex_status = fields.Selection(
        selection=[
            ("0", "Ready"),
            ("1", "Pending"),
            ("2", "Success"),
            ("3", "Error PPG"),
            ("9", "Error ERP"),
        ],
        default="0",
        string="Kardex STATUS",
    )
    kardex_picking_state = fields.Char()
    kardex_sync = fields.Boolean(default=False)
    state = fields.Selection(selection_add=[("waiting_for_kardex", "Waiting for Kardex")])

    update_button_is_visible = fields.Boolean(
        string="Update Kardex State Button Visibility", compute="_compute_update_button_is_visible", store=False
    )

    def _check_if_destination_is_kardex(self, location_id):
        return location_id.name == KARDEX_DESTINATION

    @api.depends("origin")
    def _compute_kardex(self):
        for rec in self:
            rec.kardex = False
            for model in ["stock.picking", "purchase.order", "mrp.production", "sale.order"]:
                origin = self.env[model].search([("name", "=", rec.origin)])
                if origin and origin.kardex:
                    rec.kardex = origin.kardex

    @api.depends("kardex_done", "picking_type_id")
    def _compute_update_button_is_visible(self):
        for rec in self:
            if rec.move_ids:
                all_moves_have_status_success = all([move.kardex_status == "2" for move in rec.move_ids])
                any_move_has_kardex_destination = any(
                    [self._check_if_destination_is_kardex(move.location_final_id) for move in rec.move_ids]
                )
            else:
                all_moves_have_status_success = False
                any_move_has_kardex_destination = False
            rec.update_button_is_visible = (
                not all_moves_have_status_success and rec.kardex_done and any_move_has_kardex_destination
            )

    @api.depends("move_type", "move_ids.state", "move_ids.picking_id")
    def _compute_state(self):
        res = super()._compute_state()
        for picking in self:
            if picking.kardex_picking_state == "waiting_for_kardex":
                picking.state = "waiting_for_kardex"

    def check_kardex(self):
        for picking in self:
            moves = self.env["stock.move"].search([("picking_id", "=", picking.id)])
            for move in moves:
                sql = f"SELECT Suchbegriff, Row_Update_Time FROM PPG_Artikel WHERE Suchbegriff = '{move.product_id.default_code}'"
                result = self._execute_query_on_mssql("select", sql)
                if result and result[0]["Suchbegriff"] == move.product_id.default_code:
                    move.product_id.write({"kardex": True, "kardex_done": True})
                else:
                    return

    def _check_picking_type(self):
        if self.origin and self.env["purchase.order"].search([("name", "=", self.origin)]):
            return "store"
        elif (
            self.origin
            and self.env["mrp.production"].search([("name", "=", self.origin)])
            and self.location_id.name == POST_PRODUCTION_LOCATION
        ):
            return "postproduction"
        elif self.origin and self.env["mrp.production"].search([("name", "=", self.origin)]):
            return "production"
        elif self.origin and self.env["sale.order"].search([("name", "=", self.origin)]):
            return "get"

    def _update_picking_state(self):
        for picking in self:
            kardex_moves = [move for move in picking.move_line_ids if move.kardex_running_id]
            if picking._check_picking_type() == "production":
                any_kardex_move_is_not_synced = any([not move.kardex_sync for move in kardex_moves])
                if any_kardex_move_is_not_synced:
                    picking.write({"state": "waiting_for_kardex"})
                elif not any_kardex_move_is_not_synced and picking.state == "waiting_for_kardex":
                    picking.write(
                        {
                            "state": "assigned",
                        }
                    )
                    for move in kardex_moves:
                        move.write({"picked": False})
            elif picking._check_picking_type() in ["store", "postproduction"]:
                all_moves_have_kardex_destination = all(
                    [move.location_dest_id.name == KARDEX_DESTINATION for move in kardex_moves]
                )

                any_move_has_no_sync = any([move.kardex_sync == False for move in kardex_moves])
                if all_moves_have_kardex_destination and any_move_has_no_sync:
                    picking.write({"state": "waiting_for_kardex"})

                if all_moves_have_kardex_destination and not any_move_has_no_sync:
                    # TODO : Validate Aktion ausfuehren
                    picking.write({"state": "assigned"})
            elif picking._check_picking_type() == "get":
                all_moves_have_kardex_location = all(
                    [move.location_id.name == KARDEX_DESTINATION for move in kardex_moves]
                )

                any_move_has_no_sync = any([move.kardex_sync == False for move in kardex_moves])
                if all_moves_have_kardex_location and any_move_has_no_sync:
                    picking.write({"state": "waiting_for_kardex"})

                if all_moves_have_kardex_location and not any_move_has_no_sync:
                    # TODO : Validate Aktion ausfuehren
                    picking.write({"state": "assigned"})

    def update_status_from_kardex(self):
        message_list = []
        for picking in self:
            moves = self.env["stock.move.line"].search(
                [
                    ("picking_id", "=", picking.id),
                    ("kardex_running_id", "!=", None),
                    ("kardex_status", "not in", ["2", "4"]),
                ]
            )

            for move in moves:
                kardex_running_id = move.kardex_running_id
                old_status = move.kardex_status
                sql = f"SELECT Status, Row_Update_Time FROM PPG_Auftraege WHERE BzId = {kardex_running_id}"
                result = self._execute_query_on_mssql("select_one", sql)
                if result:
                    new_status = result["Status"]
                    update_time = result["Row_Update_Time"]

                    updated = False

                    if new_status != old_status and update_time:
                        updated = True
                        move.write(
                            {
                                "kardex_status": str(new_status),
                                "kardex_row_update_time": update_time,
                            }
                        )

                    if updated:
                        message_list.append(
                            f"Kardex Status for {move.product_id.name} was updated from {old_status} to {new_status}."
                        )

                    else:
                        message_list.append(f"Kardex Status for {move.product_id.name} was not updated.")

                picking._update_picking_state()
        message = ", ".join(message_list)
        return self._create_notification(message)

    def sync_status(self):
        pickings = self.env["stock.picking"].search([("move_line_ids.kardex_status", "=", "1")])
        pickings.update_status_from_kardex()

    def sync_pickings(self):
        # all pickings with status not done

        moves = self.env["stock.move.line"].search([("kardex_status", "=", "2"), ("kardex_running_id", "!=", None)])

        picking_complete_dict = {}

        for move in moves:
            if move.kardex_running_id:
                picking_journal_ids = (
                    self.env["stock.picking.journal"]
                    .search([("kardex_running_id", "=", move.kardex_running_id)])
                    .mapped("journal_id")
                )

                sql = _get_sql_for_journal_query(move.kardex_running_id, picking_journal_ids)

                results = self._execute_query_on_mssql("select", sql)

                if results:
                    for result_counter, result in enumerate(results):
                        complete = 1

                        picking_name = result["Belegnummer"]
                        if move.picking_id.name != picking_name and move.reference != picking_name:
                            continue

                        new_journal_status = result["MaxKomplett"]
                        journal_ids = result["id_list"]
                        create_time = result["Row_Create_Time"]
                        update_time = result["Row_Update_Time"]
                        complete = max(complete, new_journal_status)
                        serial_name = result.get("Seriennummer")
                        # the journal query uses '__none__' for rows without serial/lot
                        lot_name = result.get("SerienOrCharge")
                        if lot_name == "__none__":
                            lot_name = None
                        direction = result["Richtung"]
                        product_code = result["Suchbegriff"]
                        move.write(
                            {
                                "kardex_journal_status": new_journal_status,
                                "kardex_sync": True,
                                "kardex_status": "4",
                            }
                        )

                        for journal_id in journal_ids.split(","):
                            self.env["stock.picking.journal"].create(
                                {
                                    "journal_id": journal_id,
                                    "kardex_running_id": move.kardex_running_id,
                                }
                            )

                        # get amounts for one move
                        qty_done = result["MengeErledigt"]

                        new_qty_done = qty_done
                        move_line_vals = {
                            "quantity": new_qty_done,
                            "kardex_sync": True,
                            "kardex_status": "4",
                        }

                        product_id = (
                            self.env["product.product"].search([("default_code", "=", product_code)]).mapped("id")
                        )
                        product_object = self.env["product.product"].search([("id", "=", product_id[0])])

                        if lot_name:
                            lot = (
                                self.env["stock.lot"]
                                .search([("name", "=", lot_name), ("product_id", "=", product_id[0])])
                                .mapped("id")
                            )

                            if OVERRIDE_SERIAL_FOR_STORE and direction == "3":
                                if lot:
                                    move_line_vals["lot_id"] = lot[0]

                                elif CREATE_SERIAL_FOR_STORE:
                                    try:
                                        new_lot = self.env["stock.lot"].create(
                                            {
                                                "name": lot_name,
                                                "product_id": product_id[0],
                                            }
                                        )
                                        move_line_vals["lot_id"] = new_lot.id
                                    except ValidationError as e:
                                        pass
                                else:
                                    move_line_vals["kardex_sync"] = False
                                    move_line_vals["kardex_status"] = "2"

                            if OVERRIDE_SERIAL_FOR_PRODUCTION and direction == "4":
                                if lot:
                                    move_line_vals["lot_id"] = lot[0]
                                elif CREATE_SERIAL_FOR_PRODUCTION:
                                    try:
                                        new_lot = self.env["stock.lot"].create(
                                            {
                                                "name": lot_name,
                                                "product_id": product_id[0],
                                            }
                                        )
                                        move_line_vals["lot_id"] = new_lot.id
                                    except:
                                        pass

                                else:
                                    move_line_vals["kardex_sync"] = False
                                    move_line_vals["kardex_status"] = "2"

                        if result_counter == 0:
                            move.write(move_line_vals)
                        else:
                            new_stock_move_line = move.copy(
                                {
                                    "quantity": qty_done,
                                    "lot_id": move_line_vals.get("lot_id"),
                                }
                            )

                        if picking_complete_dict.get(picking_name) is None:
                            picking_complete_dict[picking_name] = complete
                        else:
                            if complete > picking_complete_dict[picking_name]:
                                picking_complete_dict[picking_name] = complete

                        move.move_id.write({"picked": False})

        for picking_key in picking_complete_dict.keys():
            picking = self.env["stock.picking"].search([("name", "=", picking_key)])
            if picking_complete_dict[picking_key] == 1:
                picking.write({"kardex_status": "1"})
            elif picking_complete_dict[picking_key] == 2:
                picking.write({"kardex_status": "2", "kardex_sync": True, "kardex_picking_state": "synced"})

            picking._compute_state()

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            origin = vals.get("origin")
            location_dest_id = vals.get("location_dest_id")
            location_id = vals.get("location_id")
            location = self.env["stock.location"].browse(location_id)
            if origin and location_dest_id and location.name == POST_PRODUCTION_LOCATION:
                # Extract the MO name (same as origin)
                mo = self.env["mrp.production"].search([("name", "=", origin)], limit=1)
                if mo and mo.product_id and mo.product_id.last_location_id:
                    # Override the default location_dest_id
                    vals["location_dest_id"] = mo.product_id.last_location_id.id

        return super().create(vals_list)
