# stock_kardex/models/transfer.py
from odoo import fields, models

from .config import KARDEX_WAREHOUSE, ODOO_KARDEX_UNIT_FIXER, STOCK_PICKING_SEND_FLAG_FIXER


class Transfer(models.AbstractModel):
    transfer_type = fields.Char()

    def __init__(self, env, cr, uid, context=None, transfer_type=None):
        self.transfer_type = transfer_type
        super().__init__(env, cr, uid, context)

    _kardex_location = None

    @classmethod
    def get_kardex_location(cls):
        if cls._kardex_location is not None:
            cls._kardex_location = cls.env["stock.location"].search(
                [("name", "=", KARDEX_WAREHOUSE), ("usage", "=", "internal")], limit=1
            )
        return cls._kardex_location

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
        if move_line._check_picking_type() in ["store", "postproduction"]:
            return 3
        elif move_line._check_picking_type() in ["production", "get"]:
            return 4

    def transfer(self, move_line):
        transfer_type = self.transfer_type

        table = "PPG_Auftraege"

        # add ID of products zo picking vals
        picking_vals["kardex_product_id"] = move_line.product_id.kardex_product_id
        picking_vals["kardex_status"] = "1"
        picking_vals["kardex_send_flag"] = self._get_send_flag()
        picking_vals["kardex_running_id"] = self._get_kardex_running_id(move_line)
        picking_vals["kardex_unit"] = self._get_unit(move_line)
        picking_vals["kardex_quantity"] = move_line.quantity
        picking_vals["kardex_doc_number"] = move_line.picking_id.name
        if move_line.lot_id and move_line.product_id.tracking == "serial":
            picking_vals["kardex_serial"] = move_line.lot_id.name
            picking_vals["kardex_charge"] = None
        if move_line.lot_id and move_line.product_id.tracking == "lot":
            picking_vals["kardex_charge"] = move_line.lot_id.name
            picking_vals["kardex_serial"] = None
        if move_line.product_id.tracking == "none" or self._get_direction() == 4:
            picking_vals["kardex_charge"] = None
            picking_vals["kardex_serial"] = None

        picking_vals["kardex_direction"] = self._get_direction()
        picking_vals["kardex_search"] = move_line.product_id.default_code

        new_id, create_time, update_time, running_id = move_line._create_external_object(picking_vals, table)
        _logger.info(f"new_id: {new_id}")

        done_move = {
            "kardex_done": True,
            "kardex_id": new_id,
            "kardex_status": "1",
            "kardex_row_create_time": create_time,
            "kardex_row_update_time": update_time,
            "kardex_running_id": running_id,
        }

        move_line.write(done_move)
        # update product last location id
        product = move_line.product_id
        # write last location to product if it is not sale
        if self._check_picking_type() != "get":
            product.write({"last_location_id": move_line.location_dest_id})
