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
            return "store"
        elif self.picking_type_id.kardex_picking_type == "kardex_postprod":
            return "postproduction"
        elif self.picking_type_id.kardex_picking_type == "kardex_prod":
            return "production"
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
        if not self._is_kardex_db_connected():
            return False

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
            and self.move_id.location_final_id == kardex_location
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

        product = move_line.product_id
