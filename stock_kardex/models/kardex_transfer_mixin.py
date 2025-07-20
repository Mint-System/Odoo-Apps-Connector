import logging

from odoo import models

from .config import (
    KARDEX_WAREHOUSE,
    ODOO_KARDEX_UNIT_FIXER,
    STOCK_PICKING_SEND_FLAG_FIXER,
    TRANSFER_INVENTORY_MOVES,
)

_logger = logging.getLogger(__name__)


class KardexTransferMixin(models.AbstractModel):
    _name = "kardex.transfer.mixin"
    _description = "Kardex Transfer Mixin"

    def _get_kardex_location(self):
        return self.env["stock.location"].search([("name", "=", KARDEX_WAREHOUSE), ("usage", "=", "internal")], limit=1)

    def _determine_picking_type(self):
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
        elif self.move_id.is_inventory:
            _logger.info("location for inventory move: %s" % (self.move_id.location_id.name,))
            return "inventory"

    def _update_picking_state(self):
        picking_id = self.picking_id
        if picking_id and self.kardex_running_id and self.kardex_status != "4":
            picking_id.write({"kardex_picking_state": "waiting_for_kardex"})

    def send_to_kardex(self, picking_origin=None):
        _logger.info("########### SEND TO KARDEX CALLED ############")

        kardex_location = self._get_kardex_location()

        make_transfer = not self.kardex_done and not self.kardex_running_id

        _logger.info("### picking type: %s " % (self._determine_picking_type(),))
        _logger.info("### last location of product: %s " % (self.product_id.last_location_id,))
        _logger.info("### kardex_location: %s " % (kardex_location,))
        _logger.info("### picking_type_id: %s" % (self.picking_type_id,))
        _logger.info("### location_id: %s" % (self.location_id))
        _logger.info("### location_dest_id: %s" % (self.location_dest_id))
        _logger.info("### move finale location_id: %s" % (self.move_id.location_final_id))
        _logger.info("### picking destination location_id: %s" % (self.picking_id.location_dest_id))
        _logger.info("### make_transfer: %s" % (make_transfer,))

        if self._determine_picking_type() == "production" and make_transfer and self.location_id == kardex_location:
            self.transfer("production")
        elif self._determine_picking_type() == "get" and make_transfer and self.location_id == kardex_location:
            self.transfer("get")
        elif (
            self._determine_picking_type() == "postproduction"
            and make_transfer
            and self.location_dest_id == kardex_location
        ):
            self.transfer("postproduction")
        elif (
            self._determine_picking_type() == "store"
            and make_transfer
            # and self.product_id.last_location_id == kardex_location or self.move_id.location_dest_id == kardex_location
            and self.move_id.location_final_id == kardex_location
            # and self.picking_id.location_dest_id == kardex_location
        ):
            self.transfer("store")
        elif (
            self._determine_picking_type() == "inventory"
            and make_transfer
            and TRANSFER_INVENTORY_MOVES
            and (self.location_id == kardex_location or self.location_dest_id == kardex_location)
            and self.location_dest_id != self.location_id
        ):
            self.transfer("inventory")
        else:
            return

        # for picking in self:
        #     _logger.info("picking: %s" % (picking.name,))
        #     picking_vals = picking.read()[0]
        #     picking_type_id = picking_vals["picking_type_id"][0]
        #     picking_origin = picking_vals["origin"]
        #     # get moves belonging to this picking
        #     moves = self.env["stock.move"].search([("picking_id", "=", picking.id), ("product_id.kardex", "=", True)])
        #     _logger.info("### moves: %s" % (moves,))
        #     _logger.info("### quantity check: %s" % (self._check_quantities(moves),))
        #     if not moves:
        #         return
        #         # raise ValidationError("No moves found for this picking")
        #     # quantity check moved to building kardex_move_lines
        #     # if not self._check_quantities(moves):
        #     #     return
        #         # raise ValidationError("Not enough stock to send to Kardex (check quantities)")
        #     check_moves_counter = 0
        #     check_moves_list = []
        #     missing_products_message = ""

        #     for move in moves:
        #         if move.product_id.kardex and not self._check_already_in_kardex(move.product_id):
        #             check_moves_counter += 1
        #             check_moves_list.append(move.product_id.name)
        #             product_template = move.product_id.product_tmpl_id
        #             if product_template:
        #                 product_template.send_to_kardex()

        #     if check_moves_counter > 0:
        #         missing_products_message = f"The products {', '.join(check_moves_list)} were previously unknown in Kardex and were initially transferred."

        #     kardex_move_lines = picking.move_line_ids.filtered(lambda m: not m.kardex_done and not m.kardex_running_id)
        #     _logger.info("### kardex_move_lines before filter: %s" % (kardex_move_lines,))

        #     for ml in picking.move_line_ids:
        #         if ml.lot_id:
        #             quant = self.env['stock.quant'].search([
        #                 ('product_id', '=', ml.product_id.id),
        #                 ('lot_id', '=', ml.lot_id.id),
        #             #  ('quantity', '>', 0),
        #             ], limit=1)
        #             if quant:
        #                 print(f"Serial: {ml.lot_id.name} reserved at {quant.location_id.complete_name}")

        #     kardex_location = self.env["stock.location"].search(
        #         [("name", "=", KARDEX_WAREHOUSE), ("usage", "=", "internal")], limit=1
        #     )
        #     if self._check_picking_type() == "production":
        #         kardex_move_lines = kardex_move_lines.filtered(lambda m: m.location_id == kardex_location)
        #     elif self._check_picking_type() == "get":
        #         _logger.info("### quant_id: %s" % (kardex_move_lines[0].quant_id,))
        #         kardex_move_lines = kardex_move_lines.filtered(lambda m: m.location_id == kardex_location)
        #     elif self._check_picking_type() == "postproduction":
        #         kardex_move_lines = kardex_move_lines.filtered(lambda m: m.location_dest_id == kardex_location)
        #     elif self._check_picking_type() == "store":
        #         kardex_move_lines = kardex_move_lines.filtered(lambda m: m.location_dest_id == kardex_location)
        #     _logger.info("### kardex_move_lines after filter: %s" % (kardex_move_lines,))
        #     for move_line in kardex_move_lines:
        #         table = "PPG_Auftraege"

        #         # add ID of products zo picking vals
        #         picking_vals["kardex_product_id"] = move_line.product_id.kardex_product_id
        #         # create_time, update_time = self._get_dates(move, PICKING_DATE_HANDLING)
        #         # picking_vals['kardex_row_create_ime'] = create_time
        #         # picking_vals['kardex_row_update_time'] = update_time
        #         picking_vals["kardex_status"] = "1"
        #         picking_vals["kardex_send_flag"] = self._get_send_flag(picking_type_id)
        #         picking_vals["kardex_running_id"] = self._get_kardex_running_id()
        #         picking_vals["kardex_unit"] = self._get_unit(move_line.product_id.uom_id.name)
        #         picking_vals["kardex_quantity"] = move_line.quantity
        #         picking_vals["kardex_doc_number"] = picking.name
        #         if move_line.lot_id and move_line.product_id.tracking == "serial":
        #             picking_vals["kardex_serial"] = move_line.lot_id.name
        #             picking_vals["kardex_charge"] = None
        #         if move_line.lot_id and move_line.product_id.tracking == "lot":
        #             picking_vals["kardex_charge"] = move_line.lot_id.name
        #             picking_vals["kardex_serial"] = None
        #         if move_line.product_id.tracking == "none" or self._get_direction() == 4:
        #             picking_vals["kardex_charge"] = None
        #             picking_vals["kardex_serial"] = None
        #         # picking_vals["kardex_destination"] = KARDEX_DESTINATION

        #         # picking_vals["kardex_direction"] = self._get_direction(picking_origin)
        #         picking_vals["kardex_direction"] = self._get_direction()
        #         picking_vals["kardex_search"] = move_line.product_id.default_code
        #         if move_line.product_id.kardex:
        #             new_id, create_time, update_time, running_id = self._create_external_object(picking_vals, table)
        #             _logger.info(f"new_id: {new_id}")

        #             done_move = {
        #                 "kardex_done": True,
        #                 "kardex_id": new_id,
        #                 "kardex_status": "1",
        #                 "kardex_row_create_time": create_time,
        #                 "kardex_row_update_time": update_time,
        #                 "kardex_running_id": running_id,
        #             }
        #             # move_line.move_id.write(done_move)
        #             move_line.write(done_move)
        #             # update product last location id
        #             product = move_line.product_id
        #             # write last location to product if it is not sale
        #             if self._check_picking_type() != "get":
        #                 product.write({"last_location_id": move_line.location_dest_id})
        #     message = missing_products_message + "\n Kardex Picking was sent to Kardex."

        #     done_picking = {
        #         "kardex_done": True,
        #         # "kardex_row_create_time": create_time,
        #         # "kardex_row_update_time": update_time,
        #     }
        #     picking.write(done_picking)
        #     self._update_picking_state()

        #     # get all pickings belonging to the same group
        #     pickings_with_same_group = self.env["stock.picking"].search(
        #         [("group_id", "=", picking.group_id.id), ("kardex", "!=", False)]
        #     )
        #     done_picking_origin = {
        #         "kardex_done": True,
        #     }
        #     pickings_with_same_group.write(done_picking_origin)

        #     return self._create_notification(message)

    def _get_send_flag(self, move_line):
        send_flag = STOCK_PICKING_SEND_FLAG_FIXER.get(move_line.picking_type_id, "0")
        return send_flag

    def _get_kardex_running_id(self, move_line):
        sql_query = "SELECT MAX(BzId) AS maximum_running_id FROM PPG_Auftraege"
        res = move_line._execute_query_on_mssql("select_one", sql_query)
        external_max = res["maximum_running_id"] or 0

        candidate_id = external_max + 1

        # Make sure this ID is not yet used in Odoo
        StockMoveLine = self.env["stock.move.line"].sudo()
        while StockMoveLine.search_count([("kardex_running_id", "=", candidate_id)]) > 0:
            candidate_id += 1

        return int(candidate_id)

    def _get_unit(self, move_line):
        unit = move_line.product_id.uom_id.name
        fixer = ODOO_KARDEX_UNIT_FIXER
        return fixer.get(unit, unit)

    def _get_direction(self, move_line):
        if move_line._determine_picking_type() in ["store", "postproduction"]:
            return 3
        elif move_line._determine_picking_type() in ["production", "get"]:
            return 4
        elif move_line.location_dest_id == self._get_kardex_location():
            return 3
        elif move_line.location_id == self._get_kardex_location():
            return 4

    def transfer(self, transfer_type):
        move_line = self

        table = "PPG_Auftraege"
        picking_vals = {}

        # add ID of products zo picking vals
        picking_vals["kardex_product_id"] = move_line.product_id.kardex_product_id
        picking_vals["kardex_status"] = "1"
        picking_vals["kardex_send_flag"] = self._get_send_flag(move_line)
        picking_vals["kardex_running_id"] = self._get_kardex_running_id(move_line)
        picking_vals["kardex_unit"] = self._get_unit(move_line)
        picking_vals["kardex_quantity"] = move_line.quantity
        if transfer_type == "inventory":
            picking_vals["kardex_doc_number"] = move_line.reference[:15].replace(" ", "")
        else:
            picking_vals["kardex_doc_number"] = move_line.picking_id.name
        if move_line.lot_id and move_line.product_id.tracking == "serial":
            picking_vals["kardex_serial"] = move_line.lot_id.name
            picking_vals["kardex_charge"] = None
        if move_line.lot_id and move_line.product_id.tracking == "lot":
            picking_vals["kardex_charge"] = move_line.lot_id.name
            picking_vals["kardex_serial"] = None
        if move_line.product_id.tracking == "none" or self._get_direction(move_line) == 4:
            picking_vals["kardex_charge"] = None
            picking_vals["kardex_serial"] = None

        picking_vals["kardex_direction"] = self._get_direction(move_line)
        picking_vals["kardex_search"] = move_line.product_id.default_code

        new_id, create_time, update_time, running_id = move_line._create_external_object(picking_vals, table)
        _logger.info(f"new_id: {new_id}")

        if new_id:
            done_move = {
                "kardex_done": True,
                "kardex_id": new_id,
                "kardex_status": "1",
                "kardex_row_create_time": create_time,
                "kardex_row_update_time": update_time,
                "kardex_running_id": running_id,
            }

            move_line.write(done_move)
            move_line._update_picking_state()

        # update product last location id
        product = move_line.product_id
        # write last location to product if it is not sale
        # if self._determine_picking_type() != "get":
        #     product.write({"last_location_id": move_line.location_dest_id})
