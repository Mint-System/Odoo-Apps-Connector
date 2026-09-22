import logging

from odoo import models

from .config import ODOO_KARDEX_UNIT_FIXER, TRANSFER_INVENTORY_MOVES

_logger = logging.getLogger(__name__)

SDB_ORDER_TABLE = "PPG_Auftraege"

# Kardex picking type (configured on the Odoo picking type) -> transfer type
TRANSFER_TYPES = {
    "kardex_store": "store",
    "kardex_postprod": "postproduction",
    "kardex_prod": "production",
    "kardex_get": "get",
}

# SDB direction (Richtung): 3 = put into Kardex, 4 = take out of Kardex
DIRECTION_IN = 3
DIRECTION_OUT = 4


class KardexTransferMixin(models.AbstractModel):
    """Writes move lines that enter or leave the Kardex to the interface database (SDB)."""

    _name = "kardex.transfer.mixin"
    _description = "Kardex Transfer Mixin"

    def _get_kardex_location(self):
        """The one location flagged Kardex (stock_location.kardex); see its uniqueness constraint."""
        return self.env["stock.location"].search([("kardex", "=", True)], limit=1)

    def _determine_picking_type(self):
        """Transfer type of this move line, derived from the picking type (or inventory move)."""
        transfer_type = TRANSFER_TYPES.get(self.picking_type_id.kardex_picking_type)
        if transfer_type:
            return transfer_type
        if self.move_id.is_inventory:
            return "inventory"

    def _get_transfer_type(self):
        """Return the transfer type if this line must be sent to the SDB, else False.

        A line is sent when it moves stock out of (production, get, inventory) or into
        (postproduction, store, inventory) the Kardex location.
        """
        self.ensure_one()
        kardex_location = self._get_kardex_location()
        transfer_type = self._determine_picking_type()
        is_source = self.location_id == kardex_location
        is_destination = self.location_dest_id == kardex_location

        if transfer_type in ("production", "get"):
            send = is_source
        elif transfer_type == "postproduction":
            send = is_destination
        elif transfer_type == "store":
            send = self.move_id.location_final_id == kardex_location
        elif transfer_type == "inventory":
            send = (
                TRANSFER_INVENTORY_MOVES and (is_source or is_destination) and self.location_dest_id != self.location_id
            )
        else:
            send = False
        return transfer_type if send else False

    def _update_picking_state(self):
        picking_id = self.picking_id
        if picking_id and self.kardex_running_id and self.kardex_status != "4":
            picking_id.write({"kardex_picking_state": "waiting_for_kardex"})

    def send_to_kardex(self):
        """Send this move line to the SDB once, if it has to go to or from the Kardex."""
        self.ensure_one()
        if not self._is_kardex_db_connected() or self.kardex_done or self.kardex_running_id:
            return False
        transfer_type = self._get_transfer_type()
        if transfer_type:
            self.transfer(transfer_type)

    def _get_kardex_running_id(self):
        """Next free BzId: above everything in the SDB and not yet used in Odoo."""
        res = self._execute_query_on_mssql("select_one", "SELECT MAX(BzId) AS maximum_running_id FROM PPG_Auftraege")
        candidate_id = (res["maximum_running_id"] or 0) + 1

        move_lines = self.env["stock.move.line"].sudo()
        while move_lines.search_count([("kardex_running_id", "=", candidate_id)]) > 0:
            candidate_id += 1

        return int(candidate_id)

    def _get_unit(self):
        unit = self.product_id.uom_id.name
        return ODOO_KARDEX_UNIT_FIXER.get(unit, unit)

    def _get_direction(self):
        transfer_type = self._determine_picking_type()
        if transfer_type in ("store", "postproduction"):
            return DIRECTION_IN
        if transfer_type in ("production", "get"):
            return DIRECTION_OUT
        kardex_location = self._get_kardex_location()
        if self.location_dest_id == kardex_location:
            return DIRECTION_IN
        if self.location_id == kardex_location:
            return DIRECTION_OUT

    def _prepare_sdb_order_vals(self, transfer_type, running_id):
        """Values of the PPG_Auftraege row for this move line (before column mapping)."""
        self.ensure_one()
        product = self.product_id
        direction = self._get_direction()
        vals = {
            "kardex_product_id": product.kardex_product_id,
            "kardex_status": "1",
            "kardex_send_flag": "0",
            "kardex_running_id": running_id,
            "kardex_unit": self._get_unit(),
            "kardex_quantity": self.quantity,
            "kardex_doc_number": self.picking_id.name,
            "kardex_direction": direction,
            "kardex_search": product.default_code,
            "kardex_serial": None,
            "kardex_charge": None,
        }
        if transfer_type == "inventory":
            vals["kardex_doc_number"] = self.reference[:15].replace(" ", "")

        # serial/lot numbers are only sent when putting stock into the Kardex
        if self.lot_id and direction != DIRECTION_OUT:
            if product.tracking == "serial":
                vals["kardex_serial"] = self.lot_id.name
            elif product.tracking == "lot":
                vals["kardex_charge"] = self.lot_id.name
        return vals

    def transfer(self, transfer_type):
        """Write the order to PPG_Auftraege and remember the SDB ids on the move line."""
        self.ensure_one()
        vals = self._prepare_sdb_order_vals(transfer_type, self._get_kardex_running_id())
        new_id, create_time, update_time, running_id = self._create_external_object(vals, SDB_ORDER_TABLE)
        _logger.info("Kardex order %s written to SDB (%s, BzId %s)", new_id, transfer_type, running_id)

        if new_id:
            self.write(
                {
                    "kardex_done": True,
                    "kardex_id": new_id,
                    "kardex_status": "1",
                    "kardex_row_create_time": create_time,
                    "kardex_row_update_time": update_time,
                    "kardex_running_id": running_id,
                }
            )
            self.picking_id.kardex_done = True
            self._update_picking_state()
