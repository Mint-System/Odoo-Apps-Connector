import logging
import random
import string
from datetime import datetime

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

from .config import (
    CREATE_SERIAL_FOR_PRODUCTION,
    CREATE_SERIAL_FOR_STORE,
    KARDEX_DESTINATION,
    KARDEX_WAREHOUSE,
    ODOO_KARDEX_UNIT_FIXER,
    OVERRIDE_SERIAL_FOR_PRODUCTION,
    OVERRIDE_SERIAL_FOR_STORE,
    PICKING_TYPE_FIXER,
    POST_PRODUCTION_LOCATION,
    STOCK_PICKING_SEND_FLAG_FIXER,
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

    send_button_is_visible = fields.Boolean(
        string="Send to Kardex Button Visibility", compute="_compute_send_button_is_visible", store=False
    )

    update_button_is_visible = fields.Boolean(
        string="Update Kardex State Button Visibility", compute="_compute_update_button_is_visible", store=False
    )

    validate_button_is_invisible = fields.Boolean(
        string="Validate Button Visibility", compute="_compute_validate_button_is_invisible", store=False
    )

    def _check_if_destination_is_kardex(self, location_id):
        return location_id.name == KARDEX_DESTINATION

    def _check_if_location_is_kardex(self, location_id):
        return location_id.name == KARDEX_WAREHOUSE

    @api.depends("origin")
    def _compute_kardex(self):
        for rec in self:
            rec.kardex = False
            for model in ["stock.picking", "purchase.order", "mrp.production", "sale.order"]:
                origin = self.env[model].search([("name", "=", rec.origin)])
                if origin and origin.kardex:
                    rec.kardex = origin.kardex

    @api.depends("kardex_done", "picking_type_id")
    def _compute_send_button_is_visible(self):
        store_keys = [k for k, v in PICKING_TYPE_FIXER.items() if v == "store"]
        outgoing_keys = [k for k, v in PICKING_TYPE_FIXER.items() if v == "outgoing"]

        for rec in self:
            check_kardex_list = []
            for move in rec.move_ids:
                for move_line in move.move_line_ids:
                    if self._check_if_destination_is_kardex(move_line.location_dest_id):
                        check_kardex_list.append(move_line.location_dest_id.name)
            rec.send_button_is_visible = (
                not rec.kardex_done
                and len(check_kardex_list) > 0
                and (rec.picking_type_id.id in store_keys or rec.picking_type_id.id in outgoing_keys)
            )

    @api.depends("kardex_done", "picking_type_id")
    def _compute_update_button_is_visible(self):
        # store_keys = [k for k, v in PICKING_TYPE_FIXER.items() if v == "store"]
        # outgoing_keys = [k for k, v in PICKING_TYPE_FIXER.items() if v == "outgoing"]

        for rec in self:
            # import pdb; pdb.set_trace()
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

    @api.depends("send_button_is_visible")
    # def _compute_validate_button_is_invisible(self):
    #     for rec in self:
    #         if rec.move_line_ids:
    #             all_moves_has_kardex_destination = all(
    #                 self._check_if_destination_is_kardex(move.location_dest_id) for move in rec.move_line_ids
    #             )
    #         else:
    #             all_moves_has_kardex_destination = False
    #         rec.validate_button_is_invisible = not all_moves_has_kardex_destination
    def _compute_validate_button_is_invisible(self):
        for rec in self:
            rec.validate_button_is_invisible = rec.send_button_is_visible

    @api.depends("move_type", "move_ids.state", "move_ids.picking_id")
    def _compute_state(self):
        res = super()._compute_state()
        for picking in self:
            _logger.info(f"### picking.kardex_picking_state: {picking.kardex_picking_state}")
            if picking.kardex_picking_state == "waiting_for_kardex":
                picking.state = "waiting_for_kardex"

    def check_kardex(self):
        for picking in self:
            moves = self.env["stock.move"].search([("picking_id", "=", picking.id)])
            for move in moves:
                sql = f"SELECT Suchbegriff, Row_Update_Time FROM PPG_Artikel WHERE Suchbegriff = '{move.product_id.default_code}'"
                result = self._execute_query_on_mssql("select", sql)
                _logger.info("Result: %s" % (result,))
                if result and result[0]["Suchbegriff"] == move.product_id.default_code:
                    move.product_id.write({"kardex": True, "kardex_done": True})
                else:
                    return

    def _get_kardex_running_id(self):
        sql_query = "SELECT MAX(BzId) AS maximum_running_id FROM PPG_Auftraege"
        res = self._execute_query_on_mssql("select_one", sql_query)
        external_max = res["maximum_running_id"] or 0

        candidate_id = external_max + 1

        # Make sure this ID is not yet used in Odoo
        StockMoveLine = self.env["stock.move.line"].sudo()
        while StockMoveLine.search_count([("kardex_running_id", "=", candidate_id)]) > 0:
            candidate_id += 1

        return int(candidate_id)

    def _check_mp_picking(self, picking_type_id):
        return picking_type_id in [17]

    def _check_send_to_kardex(self):
        if self._check_picking_type() == "production" and self.kardex:
            return True

    def create_lot_name(self, product, index):
        return f"{product.default_code or product.name[:3].upper()}-{datetime.now().strftime('%Y%m%d%H%M%S')}-{index}"

    # def button_validate(self):
    #     # auto generate lots
    #     if CREATE_LOTS_AUTOMATICALLY:
    #         for picking in self:
    #             if picking.picking_type_code == "incoming":
    #                 new_lines = self.env["stock.move.line"]
    #                 for move_line in picking.move_line_ids:
    #                     product = move_line.product_id
    #                     if product.tracking != "none" and move_line.quantity > 0:
    #                         for i in range(int(move_line.quantity)):
    #                             lot = self.env["stock.lot"].create(
    #                                 {
    #                                     "name": self.create_lot_name(product, i + 1),
    #                                     "product_id": product.id,
    #                                     "company_id": move_line.company_id.id,
    #                                 }
    #                             )
    #                             new_line = move_line.copy(
    #                                 {
    #                                     "qty_done": 1,
    #                                     "lot_id": lot.id,
    #                                 }
    #                             )
    #                             new_lines |= new_line
    #                         move_line.unlink()

    #     _logger.info("customized button_validate called")
    #     res = super().button_validate()
    #     _logger.info("original button_validate called")
    #     for picking in self:
    #         # if self._check_picking_type() == "store":
    #         #     for move in picking.move_line_ids:
    #         #         product = move.product_id
    #         #         product.write({"last_location_id": move.location_dest_id})

    #         _logger.info("### picking type: %s" % (self._check_picking_type(),))
    #         _logger.info("### location dest: %s" % (picking.location_dest_id,))
    #         _logger.info("### destination: %s" % (self._check_if_destination_is_kardex(picking.location_dest_id),))
    #         _logger.info("### kardex_done: %s" % (picking.kardex_done,))

    #         # if self._check_picking_type() == "production" and self._check_if_destination_is_kardex(picking.location_dest_id) and not picking.kardex_done:
    #         if self._check_picking_type() == "production" and not picking.kardex_done:
    #             #self.send_to_kardex(picking.origin)
    #             pass

    #         # if self._check_picking_type() == "postproduction" and not picking.kardex_done:
    #         #     for move in picking.move_line_ids:
    #         #         product = move.product_id
    #         #         product.write({"last_location_id": move.location_dest_id})
    #         #     if self._check_if_destination_is_kardex(picking.location_dest_id):
    #         #         self.send_to_kardex(picking.origin)

    #         # if self._check_picking_type() == "get":
    #         #     self.send_to_kardex(picking.origin)

    #     _logger.info("res: %s" % (res,))
    #     return res

    def _check_is_kardex_store(self, id):
        check = False
        picking = self.env["stock.picking"].search([("id", "=", id)])
        for move in picking.move_ids:
            if move and move.picking_code == "internal" and move.location_final_id.name == KARDEX_DESTINATION:
                check = True
        return check

    def _check_is_kardex_outgoing(self, id):
        # import pdb; pdb.set_trace()
        check = False
        picking = self.env["stock.picking"].search([("id", "=", id)])
        for move in picking.move_ids:
            if move and move.picking_code == "outgoing":  # and move.location_id.name == KARDEX_DESTINATION:
                check = True
        return check

    # def action_next_transfer(self):
    #     next_transfers = super().action_next_transfer()
    #     _logger.info("next_transfers: %s" % (next_transfers,))
    #     # import pdb; pdb.set_trace()
    #     if next_transfers:
    #         if "domain" in next_transfers:
    #             pickings = self.env["stock.picking"].search(next_transfers["domain"])
    #         elif "res_id" in next_transfers:
    #             pickings = self.env["stock.picking"].search([("id", "=", next_transfers["res_id"])])
    #         for picking in pickings:
    #             write_vals = {}

    #             if picking._check_is_kardex_store(picking.id) and not picking.kardex_done:
    #                 # picking.send_to_kardex(self.origin)
    #                 pass

    #             _logger.info("### kardex outgoing: %s" % (picking._check_is_kardex_outgoing(picking.id),))

    #             write_vals["kardex"] = self.kardex
    #             picking.write(write_vals)
    #     return next_transfers

    def send_to_kardex_picking(self):
        self.send_to_kardex(PICKING_TYPE_FIXER.get(self.picking_type_id.id, None))

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
            _logger.info("### picking type: %s" % (picking._check_picking_type(),))
            kardex_moves = [move for move in picking.move_line_ids if move.kardex_running_id]
            if picking._check_picking_type() == "production":
                any_kardex_move_is_not_synced = any([not move.kardex_sync for move in kardex_moves])
                if any_kardex_move_is_not_synced:
                    _logger.info(f"### set picking {picking.name} state to waiting_for_kardex")
                    picking.write({"state": "waiting_for_kardex"})
                elif not any_kardex_move_is_not_synced and picking.state == "waiting_for_kardex":
                    _logger.info(f"### set picking {picking.name} state to assigned")
                    picking.write(
                        {
                            "state": "assigned",
                        }
                    )
                    for move in kardex_moves:
                        _logger.info("### set picked to false for move %s" % (move.name,))
                        move.write({"picked": False})
            # elif picking._check_picking_type() == "store":
            elif picking._check_picking_type() in ["store", "postproduction"]:
                all_moves_have_kardex_destination = all(
                    [move.location_dest_id.name == KARDEX_DESTINATION for move in kardex_moves]
                )

                any_move_has_no_sync = any([move.kardex_sync == False for move in kardex_moves])
                if all_moves_have_kardex_destination and any_move_has_no_sync:
                    picking.write({"state": "waiting_for_kardex"})

                if all_moves_have_kardex_destination and not any_move_has_no_sync:
                    # TODO : Validate Aktion ausfuehren
                    # picking.write({"state": "done"})
                    picking.write({"state": "assigned"})
                    # self.button_validate()
            elif picking._check_picking_type() == "get":
                all_moves_have_kardex_location = all(
                    [move.location_id.name == KARDEX_DESTINATION for move in kardex_moves]
                )
                _logger.info("all_moves_have_kardex_location: %s" % (all_moves_have_kardex_location,))

                any_move_has_no_sync = any([move.kardex_sync == False for move in kardex_moves])
                _logger.info("any_move_has_no_sync: %s" % (any_move_has_no_sync,))
                if all_moves_have_kardex_location and any_move_has_no_sync:
                    picking.write({"state": "waiting_for_kardex"})

                if all_moves_have_kardex_location and not any_move_has_no_sync:
                    # TODO : Validate Aktion ausfuehren
                    picking.write({"state": "assigned"})
                    # self.button_validate()

    # def send_to_kardex(self, picking_origin=None):
    #     for picking in self:
    #         _logger.info("picking: %s" % (picking.name,))
    #         picking_vals = picking.read()[0]
    #         picking_type_id = picking_vals["picking_type_id"][0]
    #         picking_origin = picking_vals["origin"]
    #         # get moves belonging to this picking
    #         moves = self.env["stock.move"].search([("picking_id", "=", picking.id), ("product_id.kardex", "=", True)])
    #         _logger.info("### moves: %s" % (moves,))
    #         _logger.info("### quantity check: %s" % (self._check_quantities(moves),))
    #         if not moves:
    #             return
    #             # raise ValidationError("No moves found for this picking")
    #         # quantity check moved to building kardex_move_lines
    #         # if not self._check_quantities(moves):
    #         #     return
    #             # raise ValidationError("Not enough stock to send to Kardex (check quantities)")
    #         check_moves_counter = 0
    #         check_moves_list = []
    #         missing_products_message = ""

    #         for move in moves:
    #             if move.product_id.kardex and not self._check_already_in_kardex(move.product_id):
    #                 check_moves_counter += 1
    #                 check_moves_list.append(move.product_id.name)
    #                 product_template = move.product_id.product_tmpl_id
    #                 if product_template:
    #                     product_template.send_to_kardex()

    #         if check_moves_counter > 0:
    #             missing_products_message = f"The products {', '.join(check_moves_list)} were previously unknown in Kardex and were initially transferred."

    #         kardex_move_lines = picking.move_line_ids.filtered(lambda m: not m.kardex_done and not m.kardex_running_id)
    #         _logger.info("### kardex_move_lines before filter: %s" % (kardex_move_lines,))

    #         for ml in picking.move_line_ids:
    #             if ml.lot_id:
    #                 quant = self.env['stock.quant'].search([
    #                     ('product_id', '=', ml.product_id.id),
    #                     ('lot_id', '=', ml.lot_id.id),
    #                   #  ('quantity', '>', 0),
    #                 ], limit=1)
    #                 if quant:
    #                     print(f"Serial: {ml.lot_id.name} reserved at {quant.location_id.complete_name}")

    #         kardex_location = self.env["stock.location"].search(
    #             [("name", "=", KARDEX_WAREHOUSE), ("usage", "=", "internal")], limit=1
    #         )
    #         if self._check_picking_type() == "production":
    #             kardex_move_lines = kardex_move_lines.filtered(lambda m: m.location_id == kardex_location)
    #         elif self._check_picking_type() == "get":
    #             _logger.info("### quant_id: %s" % (kardex_move_lines[0].quant_id,))
    #             kardex_move_lines = kardex_move_lines.filtered(lambda m: m.location_id == kardex_location)
    #         elif self._check_picking_type() == "postproduction":
    #             kardex_move_lines = kardex_move_lines.filtered(lambda m: m.location_dest_id == kardex_location)
    #         elif self._check_picking_type() == "store":
    #             kardex_move_lines = kardex_move_lines.filtered(lambda m: m.location_dest_id == kardex_location)
    #         _logger.info("### kardex_move_lines after filter: %s" % (kardex_move_lines,))
    #         for move_line in kardex_move_lines:
    #             table = "PPG_Auftraege"

    #             # add ID of products zo picking vals
    #             picking_vals["kardex_product_id"] = move_line.product_id.kardex_product_id
    #             # create_time, update_time = self._get_dates(move, PICKING_DATE_HANDLING)
    #             # picking_vals['kardex_row_create_ime'] = create_time
    #             # picking_vals['kardex_row_update_time'] = update_time
    #             picking_vals["kardex_status"] = "1"
    #             picking_vals["kardex_send_flag"] = self._get_send_flag(picking_type_id)
    #             picking_vals["kardex_running_id"] = self._get_kardex_running_id()
    #             picking_vals["kardex_unit"] = self._get_unit(move_line.product_id.uom_id.name)
    #             picking_vals["kardex_quantity"] = move_line.quantity
    #             picking_vals["kardex_doc_number"] = picking.name
    #             if move_line.lot_id and move_line.product_id.tracking == "serial":
    #                 picking_vals["kardex_serial"] = move_line.lot_id.name
    #                 picking_vals["kardex_charge"] = None
    #             if move_line.lot_id and move_line.product_id.tracking == "lot":
    #                 picking_vals["kardex_charge"] = move_line.lot_id.name
    #                 picking_vals["kardex_serial"] = None
    #             if move_line.product_id.tracking == "none" or self._get_direction() == 4:
    #                 picking_vals["kardex_charge"] = None
    #                 picking_vals["kardex_serial"] = None
    #             # picking_vals["kardex_destination"] = KARDEX_DESTINATION

    #             # picking_vals["kardex_direction"] = self._get_direction(picking_origin)
    #             picking_vals["kardex_direction"] = self._get_direction()
    #             picking_vals["kardex_search"] = move_line.product_id.default_code
    #             if move_line.product_id.kardex:
    #                 new_id, create_time, update_time, running_id = self._create_external_object(picking_vals, table)
    #                 _logger.info(f"new_id: {new_id}")

    #                 done_move = {
    #                     "kardex_done": True,
    #                     "kardex_id": new_id,
    #                     "kardex_status": "1",
    #                     "kardex_row_create_time": create_time,
    #                     "kardex_row_update_time": update_time,
    #                     "kardex_running_id": running_id,
    #                 }
    #                 # move_line.move_id.write(done_move)
    #                 move_line.write(done_move)
    #                 # update product last location id
    #                 product = move_line.product_id
    #                 # write last location to product if it is not sale
    #                 if self._check_picking_type() != "get":
    #                     product.write({"last_location_id": move_line.location_dest_id})
    #         message = missing_products_message + "\n Kardex Picking was sent to Kardex."

    #         done_picking = {
    #             "kardex_done": True,
    #             # "kardex_row_create_time": create_time,
    #             # "kardex_row_update_time": update_time,
    #         }
    #         picking.write(done_picking)
    #         self._update_picking_state()

    #         # get all pickings belonging to the same group
    #         pickings_with_same_group = self.env["stock.picking"].search(
    #             [("group_id", "=", picking.group_id.id), ("kardex", "!=", False)]
    #         )
    #         done_picking_origin = {
    #             "kardex_done": True,
    #         }
    #         pickings_with_same_group.write(done_picking_origin)

    #         return self._create_notification(message)

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
                        # if new_status == 2:
                        #     picking.write({"kardex_picking_state": "updated"})

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
        # pickings = self.env['stock.picking'].search([('state', '=', 'waiting_for_kardex')])
        pickings = self.env["stock.picking"].search([("move_line_ids.kardex_status", "=", "1")])
        pickings.update_status_from_kardex()

    def sync_pickings(self):
        # all pickings with status not done

        moves = self.env["stock.move.line"].search([("kardex_status", "=", "2"), ("kardex_running_id", "!=", None)])
        _logger.info(", ".join(map(str, moves.mapped("kardex_running_id"))))

        picking_complete_dict = {}

        for move in moves:
            _logger.info(f"############# MOVE: {move}")

            # if move.kardex_running_id and not move.kardex_sync:
            if move.kardex_running_id:
                picking_journal_ids = (
                    self.env["stock.picking.journal"]
                    .search([("kardex_running_id", "=", move.kardex_running_id)])
                    .mapped("journal_id")
                )
                picking_journal_ids_tuple = (
                    f"({', '.join(map(str, picking_journal_ids))})" if picking_journal_ids else "('')"
                )
                condition1 = f"WHERE BzId = {move.kardex_running_id}"
                condition2 = f"AND ID NOT IN {picking_journal_ids_tuple}"

                # sql_simple = """
                #         SELECT BzId,
                #             Seriennummer,
                #             Charge,
                #             Suchbegriff,
                #             Richtung,
                #             Row_Create_Time,
                #             Row_Update_Time,
                #             Menge AS MengeErledigt,
                #             Komplett AS MaxKomplett
                #         FROM PPG_Journal
                #         {condition1} {condition2}
                # """.format(condition1=condition1, condition2=condition2)

                sql = _get_sql_for_journal_query(condition1, condition2)

                # sql = f"""
                #     WITH CTE AS (
                #         SELECT BzId,
                #             Belegnummer,
                #             Seriennummer,
                #             Charge,
                #             Suchbegriff,
                #             Richtung,
                #             Row_Create_Time,
                #             Row_Update_Time,
                #             SUM(Menge) AS MengeErledigt,
                #             MAX(Komplett) AS MaxKomplett
                #         FROM PPG_Journal
                #         {condition1} {condition2}
                #         GROUP BY BzId, Belegnummer, Seriennummer, Charge, Suchbegriff, Richtung, Row_Create_Time, Row_Update_Time
                #     )
                #     SELECT c.BzId,
                #         c.Belegnummer,
                #         c.Seriennummer,
                #         c.Charge,
                #         c.Suchbegriff,
                #         c.Richtung,
                #         c.Row_Create_Time,
                #         c.Row_Update_Time,
                #         c.MengeErledigt,
                #         c.MaxKomplett,
                #         STUFF(
                #                 (SELECT ', ' + CAST(ID AS VARCHAR)
                #                 FROM PPG_Journal
                #                 WHERE BzId = c.BzId
                #                 {condition2}
                #                 FOR XML PATH(''), TYPE).value('.', 'NVARCHAR(MAX)'),
                #                 1, 2, ''
                #         ) AS id_list
                #     FROM CTE c;
                #     """

                # result = self._execute_query_on_mssql("select_one", sql)
                results = self._execute_query_on_mssql("select", sql)

                if results:
                    for result_counter, result in enumerate(results):
                        complete = 1

                        # _logger.info(f"##### SQL: {sql}")
                        _logger.info(f"##### PICKING OF MOVE: {move.picking_id.name}")
                        _logger.info(f"##### RESULT: {result}")
                        # if moves do not correspond ignore move line for sync
                        picking_name = result["Belegnummer"]
                        if move.picking_id.name != picking_name and move.reference != picking_name:
                            continue

                        new_journal_status = result["MaxKomplett"]
                        journal_ids = result["id_list"]
                        create_time = result["Row_Create_Time"]
                        update_time = result["Row_Update_Time"]
                        complete = max(complete, new_journal_status)
                        # complete = result["MaxKomplett"]
                        serial_name = result.get("Seriennummer")
                        # lot_name = result.get("Seriennummer") or result.get("Charge")
                        lot_name = result.get("SerienOrCharge")
                        direction = result["Richtung"]
                        product_code = result["Suchbegriff"]
                        move.write(
                            {
                                "kardex_journal_status": new_journal_status,
                                # "kardex_journal_status": complete,
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
                        _logger.info(f"### lot_name, qty_done: {lot_name}, {qty_done}")

                        # new_qty_done = move_line.qty_done #- qty_done
                        new_qty_done = qty_done
                        move_line_vals = {
                            "qty_done": new_qty_done,
                            "kardex_sync": True,
                            "kardex_status": "4",
                        }

                        product_id = (
                            self.env["product.product"].search([("default_code", "=", product_code)]).mapped("id")
                        )
                        _logger.info(f"### product_id: {product_id}")
                        product_object = self.env["product.product"].search([("id", "=", product_id[0])])
                        _logger.info(f"### product_object: {product_object.default_code}")

                        if lot_name:
                            lot = (
                                self.env["stock.lot"]
                                .search([("name", "=", lot_name), ("product_id", "=", product_id[0])])
                                .mapped("id")
                            )
                            _logger.info(f"### lot: {lot}")

                            if OVERRIDE_SERIAL_FOR_STORE and direction == "3":
                                if lot:
                                    # _logger.info(f"LOT/SN {move_line_vals['lot_id']} is overwritten with {lot[0]}")
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
                                        _logger.error("Could not complete lot handling: %s", e.name)

                                        pass
                                else:
                                    move_line_vals["kardex_sync"] = False
                                    move_line_vals["kardex_status"] = "2"

                            if OVERRIDE_SERIAL_FOR_PRODUCTION and direction == "4":
                                _logger.info(f"### lot: {lot}")
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
                                        # except ValidationError as e:
                                        #     _logger.error("Could not complete lot handling: %s", e.name)

                                        pass

                                else:
                                    move_line_vals["kardex_sync"] = False
                                    move_line_vals["kardex_status"] = "2"

                        _logger.info(f"### move_line_vals for move {move.id}: {move_line_vals}")

                        if result_counter == 0:
                            move.write(move_line_vals)
                        else:
                            new_stock_move_line = move.copy(
                                {
                                    "qty_done": qty_done,
                                    "lot_id": move_line_vals["lot_id"],
                                }
                            )

                        # move.write({"kardex_sync": True, "kardex_status": "4"})
                        _logger.info(f"### move synced with move.kardex_sync: {move.kardex_sync}")

                        # at the End of sync picking
                        _logger.info("#### at the end of sync picking:")
                        _logger.info("#### complete: %s " % (complete,))
                        _logger.info("#### serial_name: %s " % (serial_name,))
                        _logger.info("#### serial_name: %s " % (lot_name,))

                        if picking_complete_dict.get(picking_name) is None:
                            picking_complete_dict[picking_name] = complete
                        else:
                            if complete > picking_complete_dict[picking_name]:
                                picking_complete_dict[picking_name] = complete

                        move.move_id.write({"picked": False})

                        # if complete == 2 or complete == 1 or (complete == 1 and lot_name):
                        #     picking = move.picking_id
                        #     picking.write({"kardex_sync": True, "kardex_picking_state": "synced"})
                        #     picking._compute_state()
                        #     move.move_id.write({"picked": False})
                        #     _logger.info("### set picked to false for move %s" % (move.move_id.name,))
                        #     # i have to set picked = False for the moves

        for picking_key in picking_complete_dict.keys():
            picking = self.env["stock.picking"].search([("name", "=", picking_key)])
            if picking_complete_dict[picking_key] == 1:
                picking.write({"kardex_status": "1"})
            elif picking_complete_dict[picking_key] == 2:
                picking.write({"kardex_status": "2", "kardex_sync": True, "kardex_picking_state": "synced"})

            picking._compute_state()

    def _get_unit(self, unit):
        fixer = ODOO_KARDEX_UNIT_FIXER
        return fixer.get(unit, unit)

    def _get_send_flag(self, picking_type_id):
        send_flag = STOCK_PICKING_SEND_FLAG_FIXER.get(picking_type_id, "0")
        return send_flag

    # def _get_direction(self, picking_origin):
    def _get_direction(self):
        if self._check_picking_type() in ["store", "postproduction"]:
            return 3
        elif self._check_picking_type() in ["production", "get"]:
            return 4
        # if picking_origin and self.env["mrp.production"].search([("name", "=", picking_origin)]):
        #     return 4
        # return 3

    def _get_search(self):
        search_term = "".join(random.choices(string.ascii_uppercase + string.digits, k=8))

        return search_term

    def _check_quantities(self, moves):
        quantities_list = [move.quantity for move in moves]
        _logger.info(f"### quantities_list: {quantities_list}")
        return all(q > 0 for q in quantities_list)

    @api.model
    def write(self, vals):
        res = super().write(vals)

        # Check if the 'kardex_done' field is being updated
        if "kardex_done" in vals:
            for picking in self:
                # Update the 'kardex' field in related stock.move records
                picking.move_ids.write({"kardex_done": vals["kardex_done"]})

        return res

    @api.model_create_multi
    def create(self, vals_list):
        _logger.warning("################ STOCK PICKING CREATE ################")
        _logger.info("### vals_list in stock picking create %s " % (vals_list,))
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
        _logger.warning("################ END OF STOCK PICKING CREATE ################")
        return super().create(vals_list)


# class StockLot(models.Model):
#     _name = "stock.lot"
#     _description = "Stock Update Lot"
#     _inherit = ["stock.lot"]


#     @api.model_create_multi
#     def create(self, vals_list):
#         return super().create(vals_list)
