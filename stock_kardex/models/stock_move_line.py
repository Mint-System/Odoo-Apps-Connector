import logging

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import float_compare

from .config import (
    CREATE_SERIAL_FOR_PRODUCTION,
    CREATE_SERIAL_FOR_STORE,
    OVERRIDE_SERIAL_FOR_PRODUCTION,
    OVERRIDE_SERIAL_FOR_STORE,
)
from .helper import _get_sql_for_journal_query

# journal direction -> (take serial/lot from Kardex, create it if unknown)
LOT_POLICY = {
    "3": (OVERRIDE_SERIAL_FOR_STORE, CREATE_SERIAL_FOR_STORE),
    "4": (OVERRIDE_SERIAL_FOR_PRODUCTION, CREATE_SERIAL_FOR_PRODUCTION),
}

_logger = logging.getLogger(__name__)


class StockMoveLine(models.Model):
    _name = "stock.move.line"
    _inherit = ["stock.move.line", "kardex.transfer.mixin", "base.kardex.mixin"]
    _description = "Stock Move Line"

    has_kardex_location = fields.Boolean(
        string="Is Kardex Location", compute="_compute_has_kardex_location", store=False
    )
    kardex_sync = fields.Boolean(string="Mit Kardex synchronisiert", default=False)

    kardex_id = fields.Integer()
    kardex_done = fields.Boolean(string="in Kardex bekannt", default=False)
    kardex_row_create_time = fields.Char(string="Kardex Row_Create_Time")
    kardex_row_update_time = fields.Char(string="Kardex Row_Update_Time")
    kardex_status = fields.Selection(
        selection=[("0", "Ready"), ("1", "Pending"), ("2", "Success"), ("3", "Error"), ("4", "Synced")],
        default="0",
        string="Kardex STATUS",
    )
    kardex_running_id = fields.Char(string="Picking BzId")

    kardex_journal_status = fields.Char(string="Komplett")

    @api.depends("location_id", "location_dest_id")
    @api.onchange("location_id")
    def _compute_has_kardex_location(self):
        for record in self:
            record.has_kardex_location = bool(record.location_dest_id.kardex or record.location_id.kardex)

    def update_move_lines_from_kardex(self):
        """Read the order status Kardex set in PPG_Auftraege (2 = Kardex fetched the order)."""
        known_status = dict(self._fields["kardex_status"].selection)
        messages = []
        for line in self:
            old_status = line.kardex_status
            result = self._execute_query_on_mssql(
                "select_one",
                f"SELECT Status, Row_Update_Time FROM PPG_Auftraege WHERE BzId = {int(line.kardex_running_id)}",
            )
            new_status = str(result["Status"]) if result else None
            if new_status in known_status and new_status != old_status and result["Row_Update_Time"]:
                line.write({"kardex_status": new_status, "kardex_row_update_time": result["Row_Update_Time"]})
                messages.append(
                    f"Kardex Status for {line.product_id.name} was updated from {old_status} to {new_status}."
                )
            else:
                messages.append(f"Kardex Status for {line.product_id.name} was not updated.")
            line.picking_id._update_picking_state()
        return self._create_notification(", ".join(messages))

    def _fetch_journal_rows(self):
        """Journal rows Kardex wrote for the order of this line that Odoo has not processed yet."""
        running_id = int(self.kardex_running_id)
        processed = self.env["stock.picking.journal"].search([("kardex_running_id", "=", running_id)])
        return self._execute_query_on_mssql(
            "select", _get_sql_for_journal_query(running_id, processed.mapped("journal_id"))
        )

    def _resolve_lot(self, lot_name, direction):
        """Lot for the serial/lot number Kardex reported, following the LOT_POLICY.

        Returns ``(lot, ok)``; ``ok`` is False if the lot is unknown and must not be created,
        so the row has to be retried later.
        """
        lots = self.env["stock.lot"]
        override, create = LOT_POLICY.get(direction, (False, False))
        if not (lot_name and override):
            return lots, True
        lot = lots.search([("name", "=", lot_name), ("product_id", "=", self.product_id.id)], limit=1)
        if lot or not create:
            return lot, bool(lot)
        try:
            with self.env.cr.savepoint():
                return lots.create({"name": lot_name, "product_id": self.product_id.id}), True
        except ValidationError:
            _logger.warning("Lot %s could not be created for %s", lot_name, self.product_id.display_name)
            return lots, True

    def _apply_journal_row(self, row):
        """Write one journal row (quantity of one serial/lot) to this line, or to a copy of it.

        A line carries the first answer; every further answer for the same order becomes
        an additional line. Returns False if the row could not be applied yet.
        """
        lot_name = row["SerienOrCharge"]
        lot, ok = self._resolve_lot(None if lot_name == "__none__" else lot_name, row["Richtung"])
        if not ok:
            return False

        vals = {"quantity": row["MengeErledigt"], "kardex_journal_status": str(int(row["MaxKomplett"]))}
        if lot:
            vals["lot_id"] = lot.id
        if self.kardex_journal_status:
            self.copy({**vals, "kardex_status": "4", "kardex_sync": True})
        else:
            self.write(vals)
        return True

    def _is_journal_complete(self, row):
        """The order is finished when Kardex reported the ordered quantity or closed the document."""
        rounding = self.product_uom_id.rounding
        all_reported = (
            float_compare(float(row["MengeGesamt"]), float(row["MengeAuftrag"] or 0), precision_rounding=rounding) >= 0
        )
        return all_reported or int(row["BelegKomplett"]) == 2

    def sync_from_journal(self):
        """Turn the new journal rows of this line's order into quantities and lots.

        The line keeps being polled (status stays 2) until the order is complete.
        Returns the highest Komplett flag of the rows applied, 0 if there was nothing to apply.
        """
        self.ensure_one()
        complete = 0
        all_applied = True
        last_row = None
        for row in self._fetch_journal_rows():
            if self.picking_id.name != row["Belegnummer"] and self.reference != row["Belegnummer"]:
                continue
            if not self._apply_journal_row(row):
                all_applied = False
                continue
            self.env["stock.picking.journal"].create(
                [
                    {"journal_id": int(journal_id), "kardex_running_id": int(self.kardex_running_id)}
                    for journal_id in row["id_list"].split(",")
                ]
            )
            complete = max(complete, int(row["MaxKomplett"]))
            last_row = row

        if last_row:
            self.move_id.write({"picked": False})
            if all_applied and self._is_journal_complete(last_row):
                self.write({"kardex_sync": True, "kardex_status": "4"})
        return complete

    @api.model_create_multi
    def create(self, vals_list):
        res = super().create(vals_list)
        for rec in res:
            rec.send_to_kardex()
        return res
