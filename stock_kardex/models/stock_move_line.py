import logging

from odoo import api, fields, models

from .config import KARDEX_DESTINATION, KARDEX_WAREHOUSE

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

    @api.depends("location_id")
    @api.onchange("location_id")
    def _compute_has_kardex_location(self):
        kardex_destination = self.env["stock.location"].search([("name", "=", KARDEX_DESTINATION)], limit=1)
        kardex_location = self.env["stock.location"].search([("name", "=", KARDEX_WAREHOUSE)], limit=1)
        for record in self:
            record.has_kardex_location = (
                record.location_dest_id.id == kardex_destination.id or record.location_id.id == kardex_location.id
            )

    def copy_data(self, default=None):
        default = dict(default or {})
        _logger.warning("################ STOCK MOVE LINE COPY DATA ################")
        _logger.info("### default in stock move line copy data %s " % (default,))
        vals_list = super().copy_data(default=default)
        return vals_list

    def sync_move_line_status(self):
        move_lines = self.env["stock.move.line"].search(
            [
                ("kardex_running_id", "!=", None),
                ("kardex_status", "not in", ["2", "4"]),
            ]
        )
        move_lines.update_move_lines_from_kardex()

    def update_move_lines_from_kardex(self):
        message_list = []
        for move in self:
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

            if move.picking_id:
                picking = move.picking_id
                picking._update_picking_state()
        message = ", ".join(message_list)
        return self._create_notification(message)

    @api.model_create_multi
    def create(self, vals_list):
        _logger.warning("################ STOCK MOVE LINE CREATE ################")
        res = super().create(vals_list)
        for rec in res:
            rec.send_to_kardex()
        _logger.warning("################ END OF STOCK MOVE LINE CREATE ################")
        return res
