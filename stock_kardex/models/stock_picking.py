import re
import logging
import random
import string
from datetime import datetime
from collections import defaultdict

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

from .config import (
    COMPANY_ID,
    CREATE_LOTS_AUTOMATICALLY,
    CREATE_SERIAL_FOR_STORE,
    KARDEX_DESTINATION,
    KARDEX_WAREHOUSE,
    PALETTEN_WAREHOUSE,
    ODOO_KARDEX_UNIT_FIXER,
    OVERRIDE_SERIAL_FOR_STORE,
    OVERRIDE_SERIAL_FOR_PRODUCTION,
    CREATE_SERIAL_FOR_PRODUCTION,
    PICKING_TYPE_FIXER,
    POST_PRODUCTION_LOCATION,
    STOCK_PICKING_SEND_FLAG_FIXER,
    USE_BESTANDSABGLEICH_FOR_SYNC_STOCKS,
)


class StockPickingJournal(models.Model):
    _name = "stock.picking.journal"
    _description = "Stock Picking Journal"

    journal_id = fields.Integer(required=True)
    kardex_running_id = fields.Integer(string="BzId", required=True)

    _sql_constraints = [("unique_journal", "unique(journal_id)", "The Journal ID must be unique!")]

    @api.model
    def create(self, vals):
        existing = self.search([('journal_id', '=', vals.get('journal_id'))], limit=1)
        if existing:
            # Update existing record with new kardex_running_id
            existing.kardex_running_id = vals.get('kardex_running_id')
            return existing
        return super().create(vals)


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

        #Make sure this ID is not yet used in Odoo
        StockMoveLine = self.env['stock.move.line'].sudo()
        while StockMoveLine.search_count([('kardex_running_id', '=', candidate_id)]) > 0:
            candidate_id += 1 

        return int(candidate_id)

    def _check_mp_picking(self, picking_type_id):
        return picking_type_id in [17]

    def _check_send_to_kardex(self):
        if self._check_picking_type() == "production" and self.kardex:
            return True

    def create_lot_name(self, product, index):
        return f"{product.default_code or product.name[:3].upper()}-{datetime.now().strftime('%Y%m%d%H%M%S')}-{index}"


    def button_validate(self):
        # auto generate lots
        if CREATE_LOTS_AUTOMATICALLY:
            for picking in self:
                if picking.picking_type_code == "incoming":
                    new_lines = self.env["stock.move.line"]
                    for move_line in picking.move_line_ids:
                        product = move_line.product_id
                        if product.tracking != "none" and move_line.quantity > 0:
                            for i in range(int(move_line.quantity)):
                                lot = self.env["stock.lot"].create(
                                    {
                                        "name": self.create_lot_name(product, i + 1),
                                        "product_id": product.id,
                                        "company_id": move_line.company_id.id,
                                    }
                                )
                                new_line = move_line.copy(
                                    {
                                        "qty_done": 1,
                                        "lot_id": lot.id,
                                    }
                                )
                                new_lines |= new_line
                            move_line.unlink()

        _logger.info("customized button_validate called")
        res = super().button_validate()
        _logger.info("original button_validate called")
        for picking in self:
            # if self._check_picking_type() == "store":
            #     for move in picking.move_line_ids:
            #         product = move.product_id
            #         product.write({"last_location_id": move.location_dest_id})


            _logger.info("### picking type: %s" % (self._check_picking_type(),))
            _logger.info("### location dest: %s" % (picking.location_dest_id,))
            _logger.info("### destination: %s" % (self._check_if_destination_is_kardex(picking.location_dest_id),))
            _logger.info("### kardex_done: %s" % (picking.kardex_done,))

            # if self._check_picking_type() == "production" and self._check_if_destination_is_kardex(picking.location_dest_id) and not picking.kardex_done:
            if self._check_picking_type() == "production" and not picking.kardex_done:
                self.send_to_kardex(picking.origin)
                

            # if self._check_picking_type() == "postproduction" and not picking.kardex_done:
            #     for move in picking.move_line_ids:
            #         product = move.product_id
            #         product.write({"last_location_id": move.location_dest_id})
            #     if self._check_if_destination_is_kardex(picking.location_dest_id):
            #         self.send_to_kardex(picking.origin)

            # if self._check_picking_type() == "sale":
            #     self.send_to_kardex(picking.origin)

            

        _logger.info("res: %s" % (res,))
        return res

    def _check_is_kardex_store(self, id):
        check = False
        picking = self.env["stock.picking"].search([("id", "=", id)])
        for move in picking.move_ids:
            # if move and move.picking_code == "internal" and move.location_final_id.name == KARDEX_DESTINATION:
            if move and move.picking_code == "internal" and move.product_id.last_location_id.name == KARDEX_DESTINATION:
                check = True
        return check

    def _check_is_kardex_outgoing(self, id):
        #import pdb; pdb.set_trace()
        check = False
        picking = self.env["stock.picking"].search([("id", "=", id)])
        for move in picking.move_ids:
            if move and move.picking_code == "outgoing":# and move.location_id.name == KARDEX_DESTINATION:
                check = True
        return check

    def action_next_transfer(self):
        next_transfers = super().action_next_transfer()
        _logger.info("next_transfers: %s" % (next_transfers,))
        #import pdb; pdb.set_trace()
        if next_transfers:
            if "domain" in next_transfers:
                pickings = self.env["stock.picking"].search(next_transfers["domain"])
            elif "res_id" in next_transfers:
                pickings = self.env["stock.picking"].search([("id", "=", next_transfers["res_id"])])
            for picking in pickings:
                write_vals = {}

                _logger.info("### kardex store: %s" % (picking._check_is_kardex_store(picking.id),))
                _logger.info("### kardex done: %s" % (picking.kardex_done,))

                if picking._check_is_kardex_store(picking.id) and not picking.kardex_done:
                    #picking.send_to_kardex(self.origin)
                    pass
           

                _logger.info("### kardex outgoing: %s" % (picking._check_is_kardex_outgoing(picking.id),))


                write_vals["kardex"] = self.kardex
                # picking.write(write_vals)
        return next_transfers

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
            return "sale"

    def _update_picking_state(self):
        for picking in self:
            _logger.info("### picking type: %s" % (picking._check_picking_type(),))
            kardex_moves = [move for move in picking.move_line_ids if move.kardex_running_id]
            not_kardex_moves = [move for move in picking.move_line_ids if not move.kardex_running_id]
            # import pdb; pdb.set_trace()
            if picking._check_picking_type() == "production":
                any_kardex_move_is_not_synced = any([not move.kardex_sync for move in kardex_moves])
                if any_kardex_move_is_not_synced:
                    _logger.info(f"### set picking {picking.name} state to waiting_for_kardex")
                    picking.write({"state": "waiting_for_kardex"})
                elif not any_kardex_move_is_not_synced and picking.state == "waiting_for_kardex":
                    _logger.info(f"### set picking {picking.name} state to assigned")
                    picking.write({"state": "assigned",})
                    for move in kardex_moves:
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
                    # picking.write({"state": "assigned"})
                    self.button_validate()
                # for move in not_kardex_moves:
                #     move.write({"picked": True})
            elif picking._check_picking_type() == "sale":
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

    def send_to_kardex(self, picking_origin=None):
        for picking in self:
            _logger.info("picking: %s" % (picking.name,))
            picking_vals = picking.read()[0]
            picking_type_id = picking_vals["picking_type_id"][0]
            picking_origin = picking_vals["origin"]
            # get moves belonging to this picking
            moves = self.env["stock.move"].search([("picking_id", "=", picking.id), ("product_id.kardex", "=", True)])
            _logger.info("### moves: %s" % (moves,))
            _logger.info("### quantity check: %s" % (self._check_quantities(moves),))
            if not moves:
                return
                # raise ValidationError("No moves found for this picking")
            # quantity check moved to building kardex_move_lines
            # if not self._check_quantities(moves):
            #     return
                # raise ValidationError("Not enough stock to send to Kardex (check quantities)")
            check_moves_counter = 0
            check_moves_list = []
            missing_products_message = ""

            for move in moves:
                if move.product_id.kardex and not self._check_already_in_kardex(move.product_id):
                    check_moves_counter += 1
                    check_moves_list.append(move.product_id.name)
                    product_template = move.product_id.product_tmpl_id
                    if product_template:
                        product_template.send_to_kardex()

            if check_moves_counter > 0:
                missing_products_message = f"The products {', '.join(check_moves_list)} were previously unknown in Kardex and were initially transferred."

            kardex_move_lines = picking.move_line_ids.filtered(lambda m: not m.kardex_done and not m.kardex_running_id)
            _logger.info("### kardex_move_lines before filter: %s" % (kardex_move_lines,))

            for ml in picking.move_line_ids:
                if ml.lot_id:
                    quant = self.env['stock.quant'].search([
                        ('product_id', '=', ml.product_id.id),
                        ('lot_id', '=', ml.lot_id.id),
                      #  ('quantity', '>', 0),
                    ], limit=1)
                    if quant:
                        print(f"Serial: {ml.lot_id.name} reserved at {quant.location_id.complete_name}")

            kardex_location = self.env["stock.location"].search(
                [("name", "=", KARDEX_WAREHOUSE), ("usage", "=", "internal")], limit=1
            )
            if self._check_picking_type() == "production":
                kardex_move_lines = kardex_move_lines.filtered(lambda m: m.location_id == kardex_location)
            elif self._check_picking_type() == "sale":
                _logger.info("### quant_id: %s" % (kardex_move_lines[0].quant_id,))
                kardex_move_lines = kardex_move_lines.filtered(lambda m: m.location_id == kardex_location)
            elif self._check_picking_type() == "postproduction":
                kardex_move_lines = kardex_move_lines.filtered(lambda m: m.location_dest_id == kardex_location)
            elif self._check_picking_type() == "store":
                #kardex_move_lines = kardex_move_lines.filtered(lambda m: m.location_dest_id == kardex_location)
                kardex_move_lines = kardex_move_lines.filtered(lambda m: m.product_id.last_location_id == kardex_location)
            _logger.info("### kardex_move_lines after filter: %s" % (kardex_move_lines,))
            for move_line in kardex_move_lines:
                table = "PPG_Auftraege"

                # add ID of products zo picking vals
                picking_vals["kardex_product_id"] = move_line.product_id.kardex_product_id
                # create_time, update_time = self._get_dates(move, PICKING_DATE_HANDLING)
                # picking_vals['kardex_row_create_ime'] = create_time
                # picking_vals['kardex_row_update_time'] = update_time
                picking_vals["kardex_status"] = "1"
                picking_vals["kardex_send_flag"] = self._get_send_flag(picking_type_id)
                picking_vals["kardex_running_id"] = self._get_kardex_running_id()
                picking_vals["kardex_unit"] = self._get_unit(move_line.product_id.uom_id.name)
                picking_vals["kardex_quantity"] = move_line.quantity
                picking_vals["kardex_doc_number"] = picking.name
                if move_line.lot_id and move_line.product_id.tracking == "serial":
                    picking_vals["kardex_serial"] = move_line.lot_id.name
                    picking_vals["kardex_charge"] = None
                if move_line.lot_id and move_line.product_id.tracking == "lot":
                    picking_vals["kardex_charge"] = move_line.lot_id.name
                    picking_vals["kardex_serial"] = None
                if move_line.product_id.tracking == "none" or self._get_direction() == 4:
                    picking_vals["kardex_charge"] = None
                    picking_vals["kardex_serial"] = None
                # picking_vals["kardex_destination"] = KARDEX_DESTINATION

                # picking_vals["kardex_direction"] = self._get_direction(picking_origin)
                picking_vals["kardex_direction"] = self._get_direction()
                picking_vals["kardex_search"] = move_line.product_id.default_code
                if move_line.product_id.kardex:
                    new_id, create_time, update_time, running_id = self._create_external_object(picking_vals, table)
                    _logger.info(f"new_id: {new_id}")

                    _logger.info("### kardex_location: %s" % (kardex_location.name,))

                    done_move = {
                        "kardex_done": True,
                        "kardex_id": new_id,
                        "kardex_status": "1",
                        "kardex_row_create_time": create_time,
                        "kardex_row_update_time": update_time,
                        "kardex_running_id": running_id,
                      #  "location_dest_id": kardex_location.id,
                    }
                    # move_line.move_id.write(done_move)
                    move_line.write(done_move)
                    # update product last location id
                    product = move_line.product_id
                    # write last location to product if it is not sale
                    if self._check_picking_type() != "sale":
                        product.write({"last_location_id": move_line.location_dest_id})
            message = missing_products_message + "\n Kardex Picking was sent to Kardex."

            done_picking = {
                "kardex_done": True,
                # "kardex_row_create_time": create_time,
                # "kardex_row_update_time": update_time,
            }
            picking.write(done_picking)
            self._update_picking_state()

            # get all pickings belonging to the same group
            pickings_with_same_group = self.env["stock.picking"].search(
                [("group_id", "=", picking.group_id.id), ("kardex", "!=", False)]
            )
            done_picking_origin = {
                "kardex_done": True,
            }
            pickings_with_same_group.write(done_picking_origin)

            return self._create_notification(message)

    def update_status_from_kardex(self):
        message_list = []
        for picking in self:
            moves = self.env["stock.move.line"].search(
                [
                    ("picking_id", "=", picking.id),
                    ("kardex_running_id", "!=", None),
                    ("kardex_status", "!=", "2"),
                    ("kardex_sync", "!=", True),
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
                        # import pdb; pdb.set_trace()
                        if new_status == 2:
                            picking.write({"state": "assigned"})

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
        pickings = self.env["stock.picking"].search(
            [("state", "!=", "done"), ("move_line_ids.kardex_status", "=", "2")]
        )
        _logger.info(f"pickings: {pickings}")
        for picking in pickings:
            moves = self.env["stock.move.line"].search(
                [("picking_id", "=", picking.id), ("kardex_status", "=", "2"), ("kardex_running_id", "!=", None)]
            )
            _logger.info(", ".join(map(str, moves.mapped("kardex_running_id"))))

            complete = 1
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

                    sql = f"""
                        WITH CTE AS (
                            SELECT BzId,
                                Seriennummer,
                                Charge,
                                Suchbegriff,
                                Richtung,
                                Row_Create_Time,
                                Row_Update_Time,
                                SUM(Menge) AS MengeErledigt,
                                MAX(Komplett) AS MaxKomplett
                            FROM PPG_Journal
                            {condition1} {condition2}
                            GROUP BY BzId, Seriennummer, Charge, Suchbegriff, Richtung, Row_Create_Time, Row_Update_Time
                        )
                        SELECT c.BzId,
                            c.Seriennummer,
                            c.Charge,
                            c.Suchbegriff,
                            c.Richtung,
                            c.Row_Create_Time,
                            c.Row_Update_Time,
                            c.MengeErledigt,
                            c.MaxKomplett,
                            STUFF(
                                    (SELECT ', ' + CAST(ID AS VARCHAR)
                                    FROM PPG_Journal
                                    WHERE BzId = c.BzId
                                    {condition2}
                                    FOR XML PATH(''), TYPE).value('.', 'NVARCHAR(MAX)'),
                                    1, 2, ''
                            ) AS id_list
                        FROM CTE c;
                        """

                    

                    result = self._execute_query_on_mssql("select_one", sql)
                    

                    if result:
                        _logger.info(f"##### SQL: {sql}")
                        _logger.info(f"##### RESULT: {result}")
                        new_journal_status = result["MaxKomplett"]
                        journal_ids = result["id_list"]
                        create_time = result["Row_Create_Time"]
                        update_time = result["Row_Update_Time"]
                        complete = max(complete, new_journal_status)
                        # complete = result["MaxKomplett"]
                        lot_name = result.get("Seriennummer") or result.get("Charge")
                        direction = result["Richtung"]
                        product_code = result["Suchbegriff"]
                        move.write(
                            {
                                "kardex_journal_status": new_journal_status,
                                # "kardex_journal_status": complete,
                                "kardex_sync": True,
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
                        }

                        if lot_name:
                            product_id = (
                                self.env["product.product"].search([("default_code", "=", product_code)]).mapped("id")
                            )
                            _logger.info(f'### product_id: {product_id}')
                            product_object = self.env["product.product"].search([("id", "=", product_id[0])])
                            _logger.info(f'### product_object: {product_object.default_code}')
                            lot = (
                                self.env["stock.lot"]
                                .search([("name", "=", lot_name), ("product_id", "=", product_id[0])])
                                .mapped("id")
                            )
                            _logger.info(f'### lot: {lot}')

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
                                        _logger.error("Could not complete lot handling: %s", e.name)
                                        
                                        pass

                            if OVERRIDE_SERIAL_FOR_PRODUCTION and direction == "4":
                                _logger.info(f'### lot: {lot}')
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
                                        

                            if not lot:
                                move_line_vals["kardex_sync"] = False

                        _logger.info(f"### move_line_vals for move {move.id}: {move_line_vals}")

                        move.write(move_line_vals)

                        move.write({"kardex_sync": True})
                        _logger.info(f"### move synced with move.kardex_sync: {move.kardex_sync}")

            if complete == 2:
                picking.write({"kardex_sync": True})
                picking._update_picking_state()

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
        elif self._check_picking_type() in ["production", "sale"]:
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
        for vals in vals_list:
            _logger.info("### vals in stock picking create %s " % (vals,))
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


class StockMove(models.Model):
    _inherit = ["stock.move"]
    products_domain = fields.Binary(
        string="products domain",
        help="Dynamic domain used for the products that can be chosen on a move line",
        compute="_compute_products_domain",
    )
    product_id = fields.Many2one(
        "product.product",
        string="Product",
        domain="[('kardex', '=', parent.kardex)]",
    )  # this adds domain to existing domain!
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

    # tracking_type_code = fields.Char(
    #     string='Tracking Code',
    #     compute='_compute_tracking_type_code',
    #     store=False 
    # )
    tracking_type_badge = fields.Html(
        string='Tracking',
        compute='_compute_tracking_type_badge',
        sanitize=False,  # Only use if you're 100% sure your HTML is safe
        store=False
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
        for obj in self:
            if obj.picking_id.kardex:
                domain = [("kardex", "=", "True")]
            else:
                domain = []

            obj.products_domain = domain

    @api.depends('product_id')
    def _compute_tracking_type_code(self):
        for line in self:
            tracking = line.product_id.tracking
            if tracking == 'serial':
                line.tracking_type_code = 'S'
            elif tracking == 'lot':
                line.tracking_type_code = 'L'
            else:
                line.tracking_type_code = ''

    @api.depends('product_id')
    def _compute_tracking_type_badge(self):
        for line in self:
            tracking = line.product_id.tracking
            badge = ''
            if tracking == 'serial':
                badge = '<span style="background-color:#007bff;color:white;padding:2px 6px;border-radius:4px;font-size:85%;">S</span>'
            elif tracking == 'lot':
                badge = '<span style="background-color:#28a745;color:white;padding:2px 6px;border-radius:4px;font-size:85%;">L</span>'
            line.tracking_type_badge = badge

    @api.model_create_multi
    def create(self, vals_list):
        # Ensure that the product being added has kardex=True if picking has kardex=True
        _logger.info("### create move vals list %s " % (vals_list,))

        for vals in vals_list:
            picking_id = vals.get("picking_id")
            product_id = vals.get("product_id")
            location_final_id = (
                vals.get("location_final_id")
                if vals.get("location_final_id")
                else self.env["product.template"].search([("id", "=", product_id)]).location_id
            )

            if picking_id and product_id:
                # Retrieve the stock.picking record, see browse docs of odoo
                picking = self.env["stock.picking"].browse(picking_id)
                # Retirve the product
                product = self.env["product.product"].browse(vals.get("product_id"))
                if product.last_location_id:
                    _logger.info("### product last location %s " % (product.last_location_id.name,))
                if picking.kardex and not product.kardex:
                    # raise UserError(_("You can only add Kardex products."))
                    pass

                if location_final_id:
                    picking_type_code = picking.picking_type_code
                    origin_type = picking._check_picking_type()

                    if picking_type_code == "incoming" and origin_type == "store":
                        #last_location_id = self._get_destination_location_for_product(product)
                        last_location_id = product.last_location_id
                        vals["location_final_id"] = last_location_id.id

                if picking._check_picking_type() == "postproduction":
                    last_location_id = product.last_location_id
                    # last_location_id = self._get_destination_location_for_product(product)
                    vals["location_final_id"] = last_location_id.id

        records = super().create(vals_list)

        already_sent = []
        for move in records:
            picking = move.picking_id
            parent = self.env["mrp.production"].search([("name", "=", picking.origin)])
            # NEU 14.5.2025 uk
            # if not parent:
            #     parent = self.env["sale.order"].search([("name", "=", picking.origin)], limit=1)
            # _logger.info("### parent %s" % (parent.name,))
            if parent and picking.picking_type_code == "internal" and picking.id not in already_sent:
                picking.send_to_kardex(picking.origin)
                already_sent.append(picking.id)

        return records

    @api.model
    def _action_confirm(self, merge=True, merge_into=False):
        # Call super to create stock moves and pickings
        _logger.info("### _action_confirm called")

        res = super()._action_confirm(merge, merge_into)
        _logger.info("### action confirm res %s " % (res,))

        for move in res:
            picking = move.picking_id
            parent = self.env["mrp.production"].search([("name", "=", picking.origin)])

            kardex_moves = picking.move_ids.filtered(lambda move: move.product_id.kardex)

            if parent and picking and kardex_moves and not picking.kardex_done and not picking._check_picking_type() == "postproduction":
                _logger.info("### kardex outgoing called")
                picking.send_to_kardex(picking.origin)
                # pass

        return res

    # def _prepare_move_line_vals(self, quantity=None, reserved_quant=None):
    #     _logger.info("### _prepare_move_line_vals")

    #     vals = super()._prepare_move_line_vals(quantity, reserved_quant)

    #     _logger.info("### product %s " % (self.product_id.name,))
    #     _logger.info("### product last location %s " % (self.product_id.last_location_id.name,))
    #     if self.product_id.last_location_id:
    #         vals['location_dest_id'] = self.product_id.last_location_id.id
    #     _logger.info("### vals %s " % (vals,))
    #     return vals


class StockMoveLine(models.Model):
    _inherit = "stock.move.line"

    has_kardex_location = fields.Boolean(
        string="Is Kardex Location", compute="_compute_has_kardex_location", store=False
    )
    kardex_sync = fields.Boolean(string="Mit Kardex synchronisiert", default=False)

    kardex_id = fields.Integer()
    kardex_done = fields.Boolean(string="in Kardex bekannt", default=False)
    kardex_row_create_time = fields.Char(string="Kardex Row_Create_Time")
    kardex_row_update_time = fields.Char(string="Kardex Row_Update_Time")
    kardex_status = fields.Selection(
        selection=[("0", "Ready"), ("1", "Pending"), ("2", "Success"), ("3", "Error")],
        default="0",
        string="Kardex STATUS",
    )
    kardex_running_id = fields.Char(string="Picking BzId")

    kardex_journal_status = fields.Char(string="Komplett")


    # location_dest_id = fields.Many2one('stock.location', 'To', domain="[('usage', '!=', 'view')]", check_company=True, required=True, compute="_compute_location_dest_id", store=True, readonly=False, precompute=True)

    # @api.depends('move_id', 'move_id.location_id', 'move_id.location_dest_id', 'move_id.product_id.last_location_id')
    # def _compute_location_dest_id(self):
    #     for line in self:
    #         if not line.location_dest_id and line.move_id.product_id.last_location_id:
    #             line.location_dest_id = line.move_id.product_id.last_location_id

    # @api.depends('location_id', 'product_id')
    # def _compute_last_location_id(self):
    #     for record in self:
    #         record.last_location_id = record.location_id
    #         if record.product_id:
    #             last_move = self.env['stock.move'].search([
    #                 ('product_id', '=', product_id.id),
    #                 ('location_dest_id.usage', '=', 'internal'),  # Only internal locations
    #                 ('state', '=', 'done')  # Only completed moves
    #             ], order='date desc', limit=1)

    #             if last_move:
    #                 record.last_location_id = last_move.location_dest_id

    @api.depends("location_id")
    @api.onchange("location_id")
    def _compute_has_kardex_location(self):
        kardex_destination = self.env["stock.location"].search([("name", "=", KARDEX_DESTINATION)], limit=1)
        kardex_location = self.env["stock.location"].search([("name", "=", KARDEX_WAREHOUSE)], limit=1)
        # import pdb; pdb.set_trace()
        for record in self:
            record.has_kardex_location = (
                record.location_dest_id.id == kardex_destination.id or record.location_id.id == kardex_location.id
            )

            

    @api.model_create_multi
    def create(self, vals_list):
        res = super().create(vals_list)
        for vals in vals_list:
            _logger.warning("### vals in stock move line create %s " % (vals,))
            move_id = vals.get("move_id")
            move_obj = self.env["stock.move"].browse(move_id)
            picking_id = vals.get("picking_id")
            picking_obj = self.env["stock.picking"].browse(picking_id)
            product_id = vals.get("product_id")
            product_obj = self.env["product.product"].browse(product_id)
            location_id = vals.get("location_id")
            location_obj = self.env["stock.location"].browse(location_id)
            location_dest_id = vals.get("location_dest_id")
            location_dest_obj = self.env["stock.location"].browse(location_dest_id)
            _logger.warning("### move: %s " % (move_obj.name,))
            _logger.warning("### picking: %s " % (picking_obj.name,))
            _logger.warning("### picking type: %s " % (picking_obj._check_picking_type()))
            _logger.warning("### kardex done: %s " % (picking_obj.kardex_done))
            _logger.warning("### location_id: %s " % (location_obj.name,))
            _logger.warning("### location_dest_id: %s " % (location_dest_obj.name,))
           

            if picking_obj._check_picking_type() == "postproduction" and not picking_obj.kardex_done:
                
                if picking_obj._check_if_destination_is_kardex(location_dest_obj):
                    _logger.warning("### send to kardex %s " % (picking_obj.name,))
                    picking_obj.kardex_done = True
                    picking_obj.send_to_kardex(picking_obj.origin)

            if picking_obj._check_picking_type() == "sale":
                
                if picking_obj._check_if_location_is_kardex(location_obj):
                    _logger.warning("### send to kardex %s " % (picking_obj.name,))
                    picking_obj.kardex_done = True
                    picking_obj.send_to_kardex(picking_obj.origin)

            # if picking_obj._check_picking_type() == "production":
                
            #     if picking_obj._check_if_location_is_kardex(location_obj):
            #         _logger.warning("### send to kardex %s " % (picking_obj.name,))
            #         # picking_obj.kardex_done = True
            #         picking_obj.send_to_kardex(picking_obj.origin) 

            if picking_obj._check_picking_type() == "store" and not picking_obj.kardex_done:
                
                #if picking_obj._check_if_destination_is_kardex(location_dest_obj):
                #if product_obj.last_location_id.name == KARDEX_DESTINATION:
                if location_dest_obj.name == "Bestand":

                    _logger.warning("### send to kardex %s " % (picking_obj.name,))
                    # vals["location_dest_id"] = product_obj.last_location_id.id
                    
                    #picking_obj.send_to_kardex(picking_obj.origin)
                    #picking_obj.kardex_done = True
                    pass

            if picking_obj._check_is_kardex_store(picking_obj.id):
                picking_obj.write({"kardex": True})
                
        
            

        return res
    

def _get_location_base(s):
        if s:
            match = re.match(r"^[^\s-]+", s)
            return match.group(0) if match else s
        return None


def _transform_location(location):
    if _get_location_base(location) == "Shuttle":
        return "Shuttle"
    elif _get_location_base(location) == "Palette":
        return "Palette"
    return location

def _update_locations(data, transform_func):
    for item in data:
        item["LocationName"] = transform_func(item["LocationName"])
    return data  

def _harmonize_empty_values(data):
    for item in data:
        for key, value in item.items():
            if value == "" or value is None or value == '---':
                item[key] = None
    return data


class StockQuant(models.Model):
    _name = "stock.quant"
    _inherit = ["stock.quant", "base.kardex.mixin"]
    #_inherit = "stock.quant"

    def _get_location_id(self, location_name):
        location_id = self.env["stock.location"].search([("name", "=", location_name)]).mapped("id")
        return location_id


    
    def _get_data_from_bestandsabgleich(self, default_code, product_mapping):
        if default_code:
            conditions = f"WHERE Suchbegriff IN ('{default_code}')"
        else:   
            #conditions = f"WHERE Suchbegriff IN ('ZUS.P020.0000.A')" # for testing
        # conditions = f"WHERE Suchbegriff IN ('MOT.101.000.003', 'FLB.101.000.002', 'DSU.101.000.001', 'GER.101.000.000')" # for testing
            conditions = f"WHERE Suchbegriff IN {tuple(product_mapping.keys())}"
        # conditions = f"WHERE ID > {START_STOCK_SYNC}"
        # get data from PPG_Bestandsabgleich
        ppg_sql = f"""
            WITH RankedRows AS (
                SELECT
                    Suchbegriff,
                    Seriennummer,
                    Charge,
                    Row_Create_Time,
                    Bestand,
                    ROW_NUMBER() OVER (
                        PARTITION BY Suchbegriff, COALESCE(Seriennummer, 'NO_SN'), COALESCE(Charge, 'NO_LOT')
                        ORDER BY Row_Create_Time DESC
                    ) AS rn
                FROM PPG_Bestandsabgleich
                {conditions}
            )
            SELECT Suchbegriff, Seriennummer, Charge, Row_Create_Time, Bestand
            FROM RankedRows
            WHERE rn = 1
            ORDER BY Suchbegriff, Seriennummer, Charge;
        """

        ppg_data = self._execute_query_on_mssql("select", ppg_sql)

        return ppg_data



    def _get_data_direct_call(self, default_code=None, products=None):
        replace_dict = {
            "Produktnr": "Suchbegriff",
            "Lot": "Charge",
            "Serialnumber": "Seriennummer",
            "QuantityCurrent": "Bestand",
        }
        
        data = self._read_external_object_from_proddb(default_code, products)
        updated_data = [
            {replace_dict.get(k, k): v for k, v in item.items()}
            for item in data
        ]
            
        return updated_data


    @api.model
    def sync_stocks(self, default_code=None, source_sale_order=False):
        # get stock quants of Kardex Warehouse
        location_ids = self._get_location_id(KARDEX_WAREHOUSE)
        _logger.info("location_ids: %s" % (location_ids,))
        if not location_ids:
            return False

        location_id = location_ids[0]
        location_name = self.env["stock.location"].browse(location_id).name
        _logger.info("location_id: %s" % (location_id,))

        location_paletten_ids = self._get_location_id(PALETTEN_WAREHOUSE)
        _logger.info("location_paletten_ids: %s" % (location_paletten_ids,))
        if not location_paletten_ids:
            return False

        location_paletten_id = location_paletten_ids[0]
        location_paletten_name = self.env["stock.location"].browse(location_paletten_id).name
        _logger.info("location_paletten_id: %s" % (location_paletten_id,))

        # company id from settings
        company_id = COMPANY_ID

        # create dict with product ids and non empty default codes
        self.env.cr.execute("""
            SELECT pt.default_code, pp.id
            FROM product_product pp
            JOIN product_template pt ON pp.product_tmpl_id = pt.id
            WHERE pt.default_code IS NOT NULL
        """)
        product_mapping = dict(self.env.cr.fetchall())

        location_ids = (location_id, location_paletten_id)
        placeholders = ','.join(['%s'] * len(location_ids))   

        odoo_sql = "SELECT id, product_id, lot_id FROM stock_quant WHERE location_id = %s"
        self.env.cr.execute(odoo_sql, (location_id,))     

        #odoo_sql = "SELECT id, product_id, lot_id FROM stock_quant WHERE location_id IN (%s)"
        #self.env.cr.execute(odoo_sql, (location_id, location_paletten_id))

        # odoo_sql = f"SELECT id, product_id, lot_id FROM stock_quant WHERE location_id IN ({placeholders})"
        # self.env.cr.execute(odoo_sql, location_ids)
        stock_quants = self.env.cr.fetchall()

        stock_quant_mapping = {(p, l): q for q, p, l in stock_quants}

        # 2. Get existing lot_id mapping {lot_name → lot_id} for lots with location
        self.env.cr.execute("SELECT name, id FROM stock_lot WHERE location_id IS NOT NULL")
        lot_mapping = dict(self.env.cr.fetchall())  # {lot_name: lot_id}

        products = tuple(set(q[1] for q in stock_quants if q[1]))

        if not products and not default_code:
            return False  # No products to update
        

        if USE_BESTANDSABGLEICH_FOR_SYNC_STOCKS:
            kardex_data = self._get_data_from_bestandsabgleich(default_code, product_mapping)
        else:
            kardex_data = self._get_data_direct_call(default_code=default_code, products=product_mapping)

        _logger.info("### kardex_data: %s" % (kardex_data,))

        # update locations
        kardex_data = _update_locations(kardex_data, _transform_location)

        # harmonize empty values
        kardex_data = _harmonize_empty_values(kardex_data)

        _logger.info("### kardex_data: %s" % (kardex_data,))
        
        # aggregate and grouping data
        grouped = {}
        grouped2 = {} # will contain all Locations for product
        unaggregated = []

        palette_counter = 0

        for item in kardex_data:
            charge = item['Charge']
            serial = item['Seriennummer']
            suchbegriff = item['Suchbegriff']
            location = item.get('LocationName')
            if location == 'Palette':
                palette_counter += 1
            bestand = item.get('Bestand')

            if charge is None and serial is not None:
                unaggregated.append(item)  # Don't group, preserve as-is
                continue

            # Group by charge and Suchbegriff, to avoid merging unrelated products

            if charge:
                key = ('charge', charge, location, suchbegriff)
                if key not in grouped:
                    grouped[key] = {
                        'Charge': charge,
                        'Seriennummer': None,
                        'Suchbegriff': suchbegriff,
                        'LocationName': location,
                        'Bestand': 0.0,
                    }
                grouped[key]['Bestand'] += bestand
            
            else:
                key = ('no_charge', location, suchbegriff)
                if key not in grouped:
                    grouped[key] = {
                        'Charge': None,
                        'Seriennummer': None,
                        'Suchbegriff': suchbegriff,
                        'LocationName': location,
                        'Bestand': 0.0,
                    }
                grouped[key]['Bestand'] += bestand


            # if key not in grouped:
            #     grouped[key] = {
            #         'Charge': charge,
            #         'Suchbegriff': suchbegriff,
            #         'Seriennummer': serial,
            #         'Bestand': 0,
            #         'LocationName': location,
            #         'LocationNames': [],
            #     }

            # grouped[key]['Bestand'] += item['Bestand']
            # grouped[key]['LocationNames'].append(item['LocationName'])

            # group only by Suchbegriff
        for item in kardex_data:
            key2 = (suchbegriff)
            if key2 not in grouped2:
                grouped2[key2] = []
                
            grouped2[key2].append(item['LocationName'])

            _logger.info("grouped: %s" % (grouped,))
            _logger.info("grouped2: %s" % (grouped2,))
            _logger.info("unaggregated: %s" % (unaggregated,))

            for key in grouped2.keys():
                if all(x == "Shuttle" or x == "Palette" for x in grouped2[key]):
                    product = self.env["product.product"].search([("default_code", "=", default_code)], limit=1)
                    product.write({"last_location_id": location_id})

        # Convert to list if needed
        kardex_data = list(grouped.values()) + unaggregated
        _logger.info("kardex_data after grouping: %s" % (kardex_data,))


        if palette_counter == 0 and source_sale_order and default_code:
            pass

            

        # stock_dict = {
        #     product_mapping[Suchbegriff]: Bestand
        #     for Suchbegriff, Bestand in self.env.cr.fetchall()
        #     if Suchbegriff in product_mapping
        # }

        # create report for sync actions
        report = self.env['kardex.sync.report'].create({"name": "Sync Bestandsabgleich"})

        existing_quant_map = defaultdict(list)

        for row in kardex_data:
            changes = []
            default_code = row["Suchbegriff"]
            # if row["Seriennummer"] not in ("", None):
            #     lot_name = row["Seriennummer"]
            # elif row["Charge"] not in ("", None):
            #     lot_name = row["Charge"]
            # else:
            #     lot_name = None
            lot_name = row.get("Seriennummer") or row.get("Charge") or None
            _logger.info(f"### lot_name: {lot_name}")
            _logger.info(f"### lot_name not in lot_mapping: {lot_name not in lot_mapping}")
            quantity = row["Bestand"]

            product_id = product_mapping.get(default_code)
            _logger.info("### default_code: %s" % (default_code,))
            product = self.env["product.product"].search([("default_code", "=", default_code)], limit=1)
            # product_id = product.id

            _logger.info("### product_id: %s" % (product_id,))
            

            if not product_id:
                continue

            # loc_id = 

            lot_id = lot_mapping.get(lot_name) if lot_name else None
            # existing_kardex_quants_for_product = self.env["stock.quant"].search(
            #     [("product_id", "=", product_id), ("location_id", "=", location_id)]                
            # )
            # _logger.info(f"### existing_kardex_quants_for_product: {existing_kardex_quants_for_product}")


            if lot_id and (product_id, lot_id) in stock_quant_mapping:
                _logger.info("### Case 1")
                # Case 1: Update existing stock_quant record with known lot
                quant_id = stock_quant_mapping[(product_id, lot_id)]
                self.env.cr.execute(
                    """
                    UPDATE stock_quant
                    SET quantity = %s
                    WHERE id = %s
                """,
                    (quantity, quant_id),
                )
                changes.append(f"lot: {lot_name}, qty:  → {quantity}")
                existing_quant_map[product_id].append(quant_id)
                
                
            elif lot_name and (lot_name not in lot_mapping):
                # Case 2: Create a new lot if necessary
                _logger.info("### Case 2")
                self.env.cr.execute(
                    """
                    INSERT INTO stock_lot (
                        name,
                        product_id,
                        location_id,
                        create_date
                    )
                    VALUES (
                        %s,
                        %s,
                        %s,
                        NOW()
                    )
                    RETURNING id
                """,
                    (lot_name, product_id, location_id),
                )
                lot_id = self.env.cr.fetchone()[0]
                lot_mapping[lot_name] = lot_id  # Update lot mapping

                # Insert new stock_quant record for product with this lot
                self.env.cr.execute(
                    """
                    INSERT INTO stock_quant (
                        product_id,
                        lot_id,
                        quantity,
                        reserved_quantity,
                        location_id,
                        company_id,
                        in_date,
                        create_date
                    )
                    VALUES (
                        %s,
                        %s,
                        %s,
                        0,
                        %s,
                        %s,
                        NOW(),
                        NOW()
                    )
                    RETURNING id
                """,
                    (product_id, lot_id, quantity, location_id, company_id),
                )
                _logger.info(f"### data provided: product_id: {product_id}, lot_id: {lot_id}, quantity: {quantity}, location_id: {location_id}, company_id: {company_id}")
                quant_id = self.env.cr.fetchone()[0]
                changes.append(f"new lot: {lot_name}, location: {location_name} ({location_id}), qty:  → {quantity}")
                existing_quant_map[product_id].append(quant_id)
                
            else:
                if (product_id, None) in stock_quant_mapping:
                    # Case 3: Update stock_quant for product without lot

                    quant_id = stock_quant_mapping[(product_id, None)]
                    self.env.cr.execute(
                        """
                        UPDATE stock_quant
                        SET quantity = %s
                        WHERE id = %s
                    """,
                        (quantity, quant_id),
                    )
                    changes.append(f"no lot, qty:  → {quantity}")
                    existing_quant_map[product_id].append(quant_id)

                else:
                    # Case 4: Insert new stock_quant record for product with no lot which is not in stock quant

                    self.env.cr.execute(
                        """
                        INSERT INTO stock_quant (
                            product_id,
                            lot_id,
                            quantity,
                            reserved_quantity,
                            location_id,
                            company_id,
                            in_date,
                            create_date
                        )
                        VALUES (
                            %s,
                            NULL,
                            %s,
                            0,
                            %s,
                            %s,
                            NOW(),
                            NOW()
                        )
                        RETURNING id
                    """,
                        (product_id, quantity, location_id, company_id),
                    )
                    quant_id = self.env.cr.fetchone()[0]
                    existing_quant_map[product_id].append(quant_id)
                    changes.append(f"no lot, location: {location_name} ({location_id}), qty:  → {quantity} (new)")

            if changes:
                self.env['kardex.sync.report.line'].create({
                    'report_id': report.id,
                    'product_id': product.id,
                    'changes': '\n'.join(changes),
                })    

        # quants not found in data coming from kardex
        _logger.info("existing quant map: %s" % (existing_quant_map,))
        for product_id, quant_ids in existing_quant_map.items():
            quants_without_kardex_data = self.env["stock.quant"].search([("id", "not in", quant_ids), ("product_id", "=", product_id)])
            _logger.info(f"quants_without_kardex_data: {quants_without_kardex_data}")

            # set quantity to zero for these quants
            quants_without_kardex_data.write({'quantity': 0})


        # quants_without_kardex_data = existing_kardex_quants_for_product.filtered(lambda q: q.id not in kardex_quants)
        # _logger.info(f"quants_without_kardex_data: {quants_without_kardex_data}")

        # set quantity to zero for these quants
        # quants_without_kardex_data.write({'quantity': 0})




        # self._cr.commit()

        return True


# class StockLot(models.Model):
#     _name = "stock.lot"
#     _description = "Stock Update Lot"
#     _inherit = ["stock.lot"]


#     @api.model_create_multi
#     def create(self, vals_list):
#         return super().create(vals_list)
