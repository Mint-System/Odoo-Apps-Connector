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
    KARDEX_WAREHOUSE,
    COMPANY_ID,
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


class StockQuant(models.Model):
    _name = "stock.quant" 
    _description = "Stock Update Quant"
    _inherit = ["stock.quant", "base.kardex.mixin"]


    def _get_location_id(self, location_name):
        location_id = self.env["stock.location"].search([('complete_name', '=', location_name)]).mapped("id")
        return location_id


    @api.model
    def sync_stocks(self):
        # get stock quants of Kardex Warehouse
        location_ids = self._get_location_id(KARDEX_WAREHOUSE)
        if not location_ids:
            return False

        location_id = location_ids[0]

        print("location_id:", location_id)

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

        print("PRODUCT MAPPING:", product_mapping)

        # get quantities from stock quant for Kardex Warehouse
        # location_condition = f"WHERE sq.location_id = {location_id}"
        location_condition = f"WHERE location_id = {location_id}"
        # odoo_sql = """
        #     SELECT 
        #         sq.product_id, 
        #         sp.default_code AS product,
        #         sq.location_id, 
        #         sq.lot_id, 
        #         sl.name AS lot, 
        #     FROM stock_quant sq
        #     LEFT JOIN stock_lot sl ON sq.lot_id = sl.id
        #     LEFT JOIN product_product sp ON sq.product_id = sp.id
        #     {};
        # """.format(location_condition)

        odoo_sql = """
            SELECT id, product_id, lot_id FROM stock_quant
            {}
        """.format(location_condition)

        
        print("Odoo sql:", odoo_sql)

        self.env.cr.execute(odoo_sql)
        stock_quants = self.env.cr.fetchall()
        stock_quant_mapping = {(p, l): q for q, p, l in stock_quants}
        print("STOCK QUANT MAPPING", stock_quant_mapping)

        # create dict with lot ids and lot names
        # lot_ids = tuple(set(q[3] for q in stock_quants if q[3] is not None)) 
        # lot_mapping = {}
        # if lot_ids:
        #     self.env.cr.execute("SELECT id, name FROM stock_lot WHERE id IN %s", (lot_ids,))
        #     lot_mapping = dict(self.env.cr.fetchall())  # {lot_id: lot_name}

        # 2. Get existing lot_id mapping {lot_name → lot_id}
        self.env.cr.execute("SELECT id, name FROM stock_lot")
        lot_mapping = dict(self.env.cr.fetchall())  # {lot_name: lot_id}

        print("LOT MAPPING:", lot_mapping)

        products = tuple(set(q[2] for q in stock_quants if q[2]))
        # print("PRODUCTS:", products)

        if not products:
            return False  # No products to update


        # conditions = f"WHERE Suchbegriff IN ('MOT.101.000.003', 'FLB.101.000.002', 'DSU.101.000.001', 'GER.101.000.000')" # for testing
        conditions = f"WHERE Suchbegriff IN {tuple(product_mapping.keys())}"
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

        ppg_data = self._execute_query_on_mssql("select", ppg_sql)
        print("PPG DATA:", ppg_data)

        # stock_dict = {
        #     product_mapping[Suchbegriff]: Bestand
        #     for Suchbegriff, Bestand in self.env.cr.fetchall()
        #     if Suchbegriff in product_mapping
        # }




        for row in ppg_data:
            default_code = row["Suchbegriff"]
            lot_name = row["Seriennummer"]
            create_time = row["Row_Create_Time"]
            quantity = row["Bestand"]

            product_id = product_mapping.get(default_code)
            print("PRODUCT_ID:", product_id)
            if not product_id:
                continue 

            lot_id = lot_mapping.get(lot_name) if lot_name else None

            if lot_id and (product_id, lot_id) in stock_quant_mapping:
                print("CASE 1")
                # Case 1: Update existing stock_quant record with known lot
                quant_id = stock_quant_mapping[(product_id, lot_id)]
                self.env.cr.execute("""
                    UPDATE stock_quant 
                    SET quantity = %s 
                    WHERE id = %s
                """, (quantity, quant_id))
            elif lot_name and lot_name not in lot_mapping:
                # Case 2: Create a new lot if necessary
                print("CASE 2")
                self.env.cr.execute("""
                    INSERT INTO stock_lot (name, product_id, location_id, create_date) 
                    VALUES (%s, %s, %s, NOW()) 
                    RETURNING id
                """, (lot_name, product_id, location_id))
                lot_id = self.env.cr.fetchone()[0]
                lot_mapping[lot_name] = lot_id  # Update lot mapping

                # Insert new stock_quant record for product with this lot
                self.env.cr.execute("""
                    INSERT INTO stock_quant (product_id, lot_id, quantity, reserved_quantity, location_id, company_id, in_date, create_date)
                    VALUES (%s, %s, %s, 0, %s, %s, NOW(), NOW())
                """, (product_id, lot_id, quantity, location_id, company_id))
            else:
                if (product_id, None) in stock_quant_mapping:
                    # Case 3: Update stock_quant for product without lot
                    print("CASE 3")
                    quant_id = stock_quant_mapping[(product_id, None)]
                    self.env.cr.execute("""
                        UPDATE stock_quant 
                        SET quantity = %s 
                        WHERE id = %s
                    """, (quantity, quant_id))
                else:
                    # Case 4: Insert new stock_quant record for product with no lot which is not in stock quant
                    print("CASE 4")
                    self.env.cr.execute("""
                        INSERT INTO stock_quant (product_id, lot_id, quantity, reserved_quantity, location_id, company_id, in_date, create_date)
                        VALUES (%s, NULL, %s, 0, %s, %s, NOW(), NOW())
                    """, (product_id, quantity, location_id, company_id))


        

        # update
        # for record in records:
        #     self.env.cr.execute("""
        #             UPDATE stock_quant 
        #             SET quantity = %s 
        #             WHERE id = %s
        #         """, (bestand_dict[product_id], quant_id))

        # for quant_id, product_id, lot_id in stock_quants:
        #     if product_id in stock_dict:
        #         quantity = bestand_dict[product_id]
        #         lot_name = lot_mapping.get(lot_id, "No Lot")  # Lookup lot name or default "No Lot"

        #         self.env.cr.execute("""
        #             UPDATE stock_quant 
        #             SET quantity = %s 
        #             WHERE id = %s
        #         """, (quantity, quant_id))

        
        return True
