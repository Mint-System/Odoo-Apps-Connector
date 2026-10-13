import logging

from markupsafe import Markup

from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import html_escape

_logger = logging.getLogger(__name__)

JOURNAL_COLUMNS = (
    "STATUS",
    "Belegnummer",
    "Artikelid",
    "Charge",
    "Seriennummer",
    "Menge",
    "Richtung",
    "Komplett",
    "BzId",
    "Suchbegriff",
)


class KardexSimulatorWizard(models.TransientModel):
    """Plays the role of Kardex in the interface database (SDB).

    Kardex fetches an order (PPG_Auftraege.Status 1 -> 2) and reports what it did in
    PPG_Journal. The wizard writes exactly that, so Odoo's own sync can be tested end to end.
    """

    _name = "kardex.simulator.wizard"
    _inherit = ["base.kardex.mixin"]
    _description = "Kardex Answer Simulator"

    picking_id = fields.Many2one("stock.picking", required=True, readonly=True)
    scenario = fields.Selection(
        [
            ("complete", "Kardex delivers everything and closes the document"),
            ("lotchange", "Kardex delivers everything, but changes lot"),
            ("partial", "Kardex delivers a part, more follows"),
        ],
        default="complete",
        required=True,
    )
    line_ids = fields.One2many("kardex.simulator.wizard.line", "wizard_id", string="Kardex Orders")
    connection_id = fields.Many2one("base.external.mssql", readonly=True)
    simulation_allowed = fields.Boolean(readonly=True)
    sdb_report = fields.Html(string="SDB Rows", readonly=True, sanitize=False)
    show_simulate_button = fields.Boolean(compute="_compute_show_buttons")
    show_sync_button = fields.Boolean(compute="_compute_show_buttons")

    @api.depends("picking_id", "simulation_allowed")
    def _compute_show_buttons(self):
        for rec in self:
            rec.show_simulate_button = rec.simulation_allowed and not rec.picking_id.simulated 
            rec.show_sync_button = rec.simulation_allowed and not rec.picking_id.kardex_sync

    @api.model
    def default_get(self, fields_list):
        """connection_id/simulation_allowed have no field on the wizard to hang an
        @api.depends off (the value comes from base.external.mssql, not from self), so
        onchange() never re-evaluates a compute for them on a brand-new record - only
        default_get() reliably runs when the wizard is first opened. Same reasoning as
        line_ids below: fill it in here, once, when the wizard is created."""
        res = super().default_get(fields_list)
        if "connection_id" in fields_list or "simulation_allowed" in fields_list:
            connection = self.env["base.kardex.mixin"]._get_sdb()
            res["connection_id"] = connection.id
            res["simulation_allowed"] = connection.allow_simulation
        picking = self.env["stock.picking"].browse(res.get("picking_id"))
        if picking and "line_ids" in fields_list:
            open_lines = picking.move_line_ids.filtered(
                lambda line: line.kardex_running_id and line.kardex_status in ("1", "2")
            )
            seen = set()
            commands = []
            for line in open_lines:
                if line.kardex_running_id not in seen:
                    seen.add(line.kardex_running_id)
                    commands.append(Command.create(self._prepare_line_vals(line, res.get("scenario", "complete"))))
            res["line_ids"] = commands
        return res

    @api.onchange("scenario")
    def _onchange_scenario(self):
        for line in self.line_ids:
            line.answer_qty = line._default_answer_qty(self.scenario)

    # ---- reading the SDB -------------------------------------------------

    def _read_sdb_order(self, running_id):
        """The PPG_Auftraege row of an order plus the quantity Kardex reported so far."""
        running_id = int(running_id)
        order = self._execute_query_on_mssql(
            "select_one",
            "SELECT TOP 1 ID, Belegnummer, ArtikelID, Richtung, Menge, Status, Suchbegriff "
            f"FROM PPG_Auftraege WHERE BzId = {running_id}",
        )
        if not order:
            raise UserError(_("Order %s was not found in the SDB.") % running_id)
        reported = self._execute_query_on_mssql(
            "select_one", f"SELECT SUM(Menge) AS reported FROM PPG_Journal WHERE BzId = {running_id}"
        )
        order["reported"] = float((reported or {}).get("reported") or 0)
        return order

    def _prepare_line_vals(self, move_line, scenario):
        order = self._read_sdb_order(move_line.kardex_running_id)
        lot_name = move_line.lot_id.name or ""
        vals = {
            "move_line_id": move_line.id,
            "kardex_running_id": int(move_line.kardex_running_id),
            "ordered_qty": float(order["Menge"]),
            "open_qty": max(float(order["Menge"]) - order["reported"], 0.0),
            "lot_name": lot_name,
        }
        vals["answer_qty"] = self.env["kardex.simulator.wizard.line"]._default_answer_qty(scenario, vals["open_qty"])
        return vals

    def action_read_sdb(self):
        """Show the rows of this picking's orders in PPG_Auftraege and PPG_Journal."""
        self.ensure_one()
        running_ids = ", ".join(str(int(line.kardex_running_id)) for line in self.line_ids) or "0"
        orders = self._execute_query_on_mssql(
            "select",
            "SELECT ID, BzId, Belegnummer, Richtung, Menge, Status, Row_Create_Time, Row_Update_Time "
            f"FROM PPG_Auftraege WHERE BzId IN ({running_ids}) ORDER BY BzId",
        )
        journal = self._execute_query_on_mssql(
            "select",
            "SELECT ID, BzId, Belegnummer, Charge, Seriennummer, Menge, Komplett, STATUS, Row_Create_Time "
            f"FROM PPG_Journal WHERE BzId IN ({running_ids}) ORDER BY ID",
        )
        self.sdb_report = self._render_table("PPG_Auftraege", orders) + self._render_table("PPG_Journal", journal)
        return self._reopen()

    @staticmethod
    def _render_table(title, rows):
        if not rows:
            return Markup("<p><b>%s</b>: -</p>") % title
        header = Markup("").join(Markup("<th>%s</th>") % column for column in rows[0])
        body = Markup("").join(
            Markup("<tr>%s</tr>")
            % Markup("").join(Markup("<td>%s</td>") % html_escape(str(value)) for value in row.values())
            for row in rows
        )
        return Markup("<p><b>%s</b></p><table class='table table-sm'><tr>%s</tr>%s</table>") % (title, header, body)

    # ---- writing the SDB -------------------------------------------------

    def _check_simulation_allowed(self):
        connection = self.connection_id
        if not connection.allow_simulation:
            raise UserError(
                _(
                    "The active SDB connection '%s' does not allow simulation. Use a test database and tick "
                    "'Allow Kardex Simulation' on its connection.",
                    connection.name or "-",
                )
            )

    def _journal_rows(self, line, order, komplett=1):
        """The PPG_Journal rows Kardex would write for one order (serials one by one)."""
        qty = line.answer_qty
        if qty <= 0:
            return []
        row = {
            "STATUS": 1,
            "Belegnummer": order["Belegnummer"],
            "Artikelid": order["ArtikelID"],
            "Charge": None,
            "Seriennummer": None,
            "Menge": qty,
            "Richtung": str(order["Richtung"]),
            "Komplett": komplett,
            "BzId": line.kardex_running_id,
            "Suchbegriff": order["Suchbegriff"],
        }
        tracking = line.move_line_id.product_id.tracking
        if tracking == "serial":
            if self.scenario == "lotchange":
                return [
                    {**row, "Seriennummer": f"{line.lot_name}-{number}", "Menge": 1.0} for number in range(1, int(qty) + 1)
                ]
            else:
                row["Seriennummer"] = line.lot_name
        if tracking == "lot":
            row["Charge"] = line.lot_name
        return [row]

    def action_simulate_answer(self):
        """Kardex fetches the orders and reports them in the journal."""
        self.ensure_one()
        self._check_simulation_allowed()

        rows = []
        for line in self.line_ids:
            order = self._read_sdb_order(line.kardex_running_id)
            if order["Status"] not in (1, 2):
                raise UserError(
                    _(
                        "Order %(bzid)s has status %(status)s in the SDB.",
                        bzid=line.kardex_running_id,
                        status=order["Status"],
                    )
                )
            rows += self._journal_rows(line, order)
        if not rows:
            raise UserError(_("Nothing to report: the answer quantity is 0."))
        if self.scenario in ["complete","lotchange"]:
            rows[-1]["Komplett"] = 2

        placeholder = self._sql_placeholder()
        for line in self.line_ids:
            self._execute_query_on_mssql(
                "update",
                f"UPDATE PPG_Auftraege SET Status = 2 WHERE BzId = {placeholder} AND Status = 1",
                (line.kardex_running_id,),
            )
        columns = ", ".join(JOURNAL_COLUMNS)
        placeholders = ", ".join([placeholder] * len(JOURNAL_COLUMNS))
        insert = f"INSERT INTO PPG_Journal ({columns}) VALUES ({placeholders})"
        for row in rows:
            self._execute_query_on_mssql("insert", insert, tuple(row[column] for column in JOURNAL_COLUMNS))

        self.picking_id.message_post(
            body=_(
                "Kardex answer simulated for BzId %(bzids)s (%(count)s journal rows).",
                bzids=", ".join(str(line.kardex_running_id) for line in self.line_ids),
                count=len(rows),
            )
        )
        self.picking_id.write({"simulated": True})
        return self.action_read_sdb()

    def action_sync_now(self):
        """Run Odoo's real status and journal sync for this picking."""
        self.ensure_one()
        self.picking_id.sync_status()
        self.picking_id.sync_pickings()
        return self.action_read_sdb()

    def _reopen(self):
        return {
            "type": "ir.actions.act_window",
            "name": _("Kardex Simulator"),
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }


class KardexSimulatorWizardLine(models.TransientModel):
    _name = "kardex.simulator.wizard.line"
    _description = "Kardex Answer Simulator Line"

    wizard_id = fields.Many2one("kardex.simulator.wizard", required=True, ondelete="cascade")
    move_line_id = fields.Many2one("stock.move.line", required=True, readonly=True)
    product_id = fields.Many2one(related="move_line_id.product_id")
    kardex_running_id = fields.Integer(string="BzId", readonly=True)
    ordered_qty = fields.Float(readonly=True)
    open_qty = fields.Float(string="Still Open", readonly=True)
    answer_qty = fields.Float(string="Kardex Delivers")
    lot_name = fields.Char(string="Serial/Lot", help="Serial numbers are numbered: <name>-1, <name>-2 ...")

    def _default_answer_qty(self, scenario, open_qty=None):
        open_qty = self.open_qty if open_qty is None else open_qty
        return open_qty if scenario in ["complete","lotchange"] else float(int(open_qty / 2)) or open_qty
