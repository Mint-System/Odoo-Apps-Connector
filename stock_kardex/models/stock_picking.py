import logging
import random
import string

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

from .config import (
    ODOO_KARDEX_UNIT_FIXER,
    PICKING_AUTO,
    STOCK_PICKING_DIRECTION_FIXER,
    STOCK_PICKING_SEND_FLAG_FIXER,
    START_STOCK_SYNC,
)


class StockPickingJournal(models.Model):
    _name = "stock.picking.journal" 
    _description = "Stock Picking Journal"

    journal_id = fields.Integer(string='Journal Id', required=True)
    kardex_running_id = fields.Integer(string='BzId', required=True)

    _sql_constraints = [
        ('unique_journal', 'unique(journal_id)', 
         'The Journal ID must be unique!')
    ]

class StockPicking(models.Model):
    _name = "stock.picking"
    _inherit = ["stock.picking", "base.kardex.mixin"]
    _description = "Stock Kardex Picking"

    kardex = fields.Boolean(string="Kardex", default=False)
    kardex_id = fields.Integer(string="Kardex Id")
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
    kardex_sync = fields.Boolean(string="Kardex Sync", default=False)


    def check_kardex(self):
        for picking in self:
            moves = self.env["stock.move"].search([("picking_id", "=", picking.id)])
            for move in moves:
                sql = f"SELECT Suchbegriff, Row_Update_Time FROM PPG_Artikel WHERE Suchbegriff = '{move.product_id.default_code}'"
                result = self._execute_query_on_mssql("select", sql)
                print("Result: %s" % (result,))
                if result and result[0]["Suchbegriff"] == move.product_id.default_code:
                    move.product_id.write({"kardex": True, "kardex_done": True})

    def _get_kardex_running_id(self):
        # Find the current maximum kardex_running_id
        # max_kardex_product_id = self.env['product.template'].search([('kardex_product_id', '>', '0')], order='kardex_product_id desc', limit=1).kardex_product_id

        sql_query = "SELECT Max(BzId) AS maximum_running_id FROM PPG_Auftraege"
        res = self._execute_query_on_mssql("select_one", sql_query)
        max_kardex_running_id = res["maximum_running_id"]
        kardex_running_id = max_kardex_running_id + 1 if max_kardex_running_id else 1
        return int(kardex_running_id)


    @api.model
    def create(self, vals):
        record = super().create(vals)
        print("VALS:", vals)
        picking_type_id = vals["picking_type_id"]

        if picking_type_id == 1: # purchase
            model = "purchase.order"
        elif picking_type_id == 17: # production
            model = "mrp.production"

        if picking_type_id in [1, 17]:
            kardex = self.env[model].search([("name", "=", vals['origin'])]).mapped("kardex")

            record["kardex"] = kardex[0]

        return record

    
    def action_assign(self):
        """ Check availability of picking moves.
        This has the effect of changing the state and reserve quants on available moves, and may
        also impact the state of the picking as it is computed based on move's states.
        @return: True
        """
        self.mapped('package_level_ids').filtered(lambda pl: pl.state == 'draft' and not pl.move_ids)._generate_moves()
        self.filtered(lambda picking: picking.state == 'draft').action_confirm()
        moves = self.move_ids.filtered(lambda move: move.state not in ('draft', 'cancel', 'done')).sorted(
            key=lambda move: (-int(move.priority), not bool(move.date_deadline), move.date_deadline, move.date, move.id)
        )
        if not moves:
            raise UserError(_('Nothing to check the availability for.'))
        moves._action_assign()
        all_moves_assigned = all(move.state == 'assigned' for move in moves)
        if all_moves_assigned and PICKING_AUTO:
            self.send_to_kardex()


        return True



    def send_to_kardex(self):
        for picking in self:
            picking_vals = picking.read()[0]
            # get moves belonging to this picking
            moves = self.env["stock.move"].search([("picking_id", "=", picking.id), ("product_id.kardex", "=", True)])
            if not moves:
                raise ValidationError("No moves found for this picking")
            if not self._check_quantities(moves):
                raise ValidationError(
                    "Not enough stock to send to Kardex (check quantities)"
                )
            check_moves_counter = 0
            check_moves_list = []
            for move in moves:
                print(f"Product: {move.product_id.name}")
                if move.product_id.kardex and not move.product_id.kardex_done:
                    check_moves_counter += 1
                    check_moves_list.append(move.product_id.name)

            if check_moves_counter > 0:
                raise ValidationError(
                    f"These Products are unknown in Kardex: {', '.join(check_moves_list)}. Please transfer Products to Kardex."
                )
                return

            # create external object for every picking record
            for move in moves:
                table = "PPG_Auftraege"
                picking_type_id = picking_vals["picking_type_id"][0]
                # add ID of products zo picking vals
                picking_vals["kardex_product_id"] = move.product_id.kardex_product_id
                # create_time, update_time = self._get_dates(move, PICKING_DATE_HANDLING)
                # picking_vals['kardex_row_create_time'] = create_time
                # picking_vals['kardex_row_update_time'] = update_time
                picking_vals["kardex_status"] = "1"
                picking_vals["kardex_send_flag"] = self._get_send_flag(picking_type_id)
                picking_vals["kardex_running_id"] = self._get_kardex_running_id()
                picking_vals["kardex_unit"] = self._get_unit(move.product_id.uom_id.name)
                picking_vals["kardex_quantity"] = move.quantity
                picking_vals["kardex_doc_number"] = picking.name
                
                picking_vals["kardex_direction"] = self._get_direction(picking_type_id)
                picking_vals["kardex_search"] = move.product_id.default_code
                if move.product_id.kardex:
                    new_id, create_time, update_time, running_id = self._create_external_object(
                        picking_vals, table
                    )
                    _logger.info("new_id: {}".format(new_id))

                    done_move = {
                        "kardex_done": True,
                        "kardex_id": new_id,
                        "kardex_status": "1",
                        "kardex_row_create_time": create_time,
                        "kardex_row_update_time": update_time,
                        "kardex_running_id": running_id,
                    }
                    move.write(done_move)
            message = "Kardex Picking was sent to Kardex."

            done_picking = {
                "kardex_done": True,
                "kardex_row_create_time": create_time,
                "kardex_row_update_time": update_time,
            }
            picking.write(done_picking)
            return self._create_notification(message)

    def update_status_from_kardex(self):
        message_list = []
        for picking in self:
            moves = self.env["stock.move"].search([("picking_id", "=", picking.id)])
            for move in moves:
                kardex_id = move.kardex_id
                old_status = move.kardex_status
                sql = f"SELECT Status, Row_Update_Time FROM PPG_Auftraege WHERE ID = {kardex_id}"
                result = self._execute_query_on_mssql("select_one", sql)
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
                    message_list.append(
                        f"Kardex Status for {move.product_id.name} was not updated."
                    )

        message = ", ".join(message_list)
        return self._create_notification(message)

    def sync_pickings(self):
        # all pickings with status not done
        pickings = self.env["stock.picking"].search([("state", "!=", 'done')])
        for picking in pickings:
            print("Picking:", picking.name)
            moves = self.env["stock.move"].search([("picking_id", "=", picking.id)])
            
            complete = 1
            for move in moves:
                # if move.kardex_running_id and not move.kardex_sync:
                if move.kardex_running_id:
                    picking_journal_ids = self.env["stock.picking.journal"].search([("kardex_running_id", "=", move.kardex_running_id)]).mapped("journal_id")
                    picking_journal_ids_tuple = f"({', '.join(map(str, picking_journal_ids))})" if picking_journal_ids else "('')"
                    condition1 = f"WHERE BzId = {move.kardex_running_id}"
                    condition2 = f"AND ID NOT IN {picking_journal_ids_tuple}"
                    sql = """
                        WITH CTE AS (
                            SELECT BzId, 
                                Seriennummer,
                                Row_Create_Time,
                                Row_Update_Time,
                                SUM(Menge) AS MengeErledigt,
                                MAX(Komplett) AS MaxKomplett
                            FROM PPG_Journal
                            {condition1} {condition2}
                            GROUP BY BzId, Seriennummer, Row_Create_Time, Row_Update_Time
                        )
                        SELECT c.BzId, 
                            c.Seriennummer,
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
                        """.format(condition1=condition1, condition2=condition2)

                    result = self._execute_query_on_mssql("select_one", sql)
                    
                    if result:
                        print("MengeErledigt", result["MengeErledigt"])
                        print("MaxKomplett:", result["MaxKomplett"])
                        new_journal_status = result["MaxKomplett"] 
                        journal_ids = result["id_list"] 
                        create_time = result["Row_Create_Time"]
                        update_time = result["Row_Update_Time"]   
                        complete = max(complete, new_journal_status)  
                        #complete = result["MaxKomplett"]
                        lot_name = result["Seriennummer"]  
                        move.write(
                            {
                                "kardex_journal_status": new_journal_status,
                                #"kardex_journal_status": complete,
                                "kardex_sync": True
                            }
                        )   

                        for journal_id in journal_ids.split(','):
                            self.env['stock.picking.journal'].create({
                                'journal_id': journal_id,
                                'kardex_running_id': move.kardex_running_id,
                            })

                        # get amounts for one move
                        qty_done = result["MengeErledigt"]
                        print("MengeErledigt:", qty_done)

                        # update qty_done for move lines
                        move_lines = self.env["stock.move.line"].search([("move_id", "=", move.id)])
                        for move_line in move_lines:
                            new_qty_done = move_line.qty_done + qty_done
                            move_line_vals = {
                                "qty_done": new_qty_done
                            }
                            if lot_name:
                                lot_id = self.env["stock.lot"].search([("name", "=", lot_name)]).mapped("id")[0]
                                move_line_vals["lot_id"] = lot_id

                            move_line.write(move_line_vals)
                        
                        move.write({"kardex_sync": True})

            # if complete == 1:
            #     # copy picking
            #     new_pickings = self.copy(default={"kardex_sync": False})
            #     if len(new_pickings) == 1:
            #         new_picking = new_pickings[0]

            #         for move in new_picking:
            #             product_uom_qty = new_amounts_dict[move.kardex_running_id]
            #             move.write(
            #                 {
            #                     "product_uom_qty": product_uom_qty,
            #                     "kardex_running_id": "",
            #                 }
            #             )

                
            #elif complete == 2: 
            if complete == 2:
                picking.write({"state": "done", "kardex_sync": True})


    

    def _get_unit(self, unit):
        fixer = ODOO_KARDEX_UNIT_FIXER
        return fixer.get(unit, unit)
    
    def _get_send_flag(self, picking_type_id):
        send_flag = STOCK_PICKING_SEND_FLAG_FIXER[picking_type_id]
        return send_flag
    

    def _get_direction(self, picking_type_id):
        direction = STOCK_PICKING_DIRECTION_FIXER[picking_type_id]
        # direction = 4
        return direction

    def _get_search(self):
        search_term = "".join(
            random.choices(string.ascii_uppercase + string.digits, k=8)
        )

        return search_term

    def _check_quantities(self, moves):
        quantities_list = [move.quantity for move in moves]
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
    )
    kardex_running_id = fields.Char(string="Picking BzId")
    kardex_sync = fields.Boolean(string="Kardex Sync", default=False)
    kardex_journal_status = fields.Char(string="Komplett")

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

    @api.model
    def create(self, vals):
        # Ensure that the product being added has kardex=True if picking has kardex=True
        picking_id = vals.get("picking_id")
        product_id = vals.get("product_id")

        if picking_id and product_id:
            # Retrieve the stock.picking record, see browse docs of odoo
            picking = self.env["stock.picking"].browse(picking_id)
            # Retirve the product
            product = self.env["product.product"].browse(vals.get("product_id"))
            if picking.kardex and not product.kardex:
                raise UserError("You can only add Kardex products.")
        return super().create(vals)


    def sync_stocks(self):
        conditions = f"WHERE Suchbegriff IN ('MOT.101.000.003', 'FLB.101.000.002', 'DSU.101.000.001', 'GER.101.000.000')"
        # conditions = f"WHERE ID > {START_STOCK_SYNC}"
        # get data from PPG_Bestandsabgleich
        ppg_sql = """
            WITH RankedRows AS (
                SELECT 
                    Suchbegriff, 
                    Seriennummer, 
                    Row_Create_Time, 
                    Bestand,
                    ROW_NUMBER() OVER (
                        PARTITION BY Suchbegriff, COALESCE(Seriennummer, 'NO_SN') 
                        ORDER BY Row_Create_Time DESC
                    ) AS rn
                FROM PPG_Bestandsabgleich
                {}
            )
            SELECT Suchbegriff, Seriennummer, Row_Create_Time, Bestand
            FROM RankedRows
            WHERE rn = 1
            ORDER BY Suchbegriff, Seriennummer;
        """.format(conditions)

        odoo_sql = """
            SELECT 
                sq.id, 
                sq.product_id, 
                sq.location_id, 
                sq.lot_id, 
                sl.name AS lot, 
                sloc.complete_name AS location_name, 
                sq.quantity
            FROM stock_quant sq
            LEFT JOIN stock_lot sl ON sq.lot_id = sl.id
            LEFT JOIN stock_location sloc ON sq.location_id = sloc.id;
        """

        self.env.cr.execute(odoo_sql)
        result = self.env.cr.fetchall()
        print(result)
        return result
