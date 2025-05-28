from odoo import api, fields, models

class StockQuant(models.Model):
    _name = "stock.quant"
    _inherit = ["stock.quant", "base.kardex.mixin"]
    _description = "Stock Quant"
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
    def sync_stocks(self, default_code=None):
        # get stock quants of Kardex Warehouse
        location_ids = self._get_location_id(KARDEX_WAREHOUSE)
        _logger.info("location_ids: %s" % (location_ids,))
        if not location_ids:
            return False

        location_id = location_ids[0]
        location_name = self.env["stock.location"].browse(location_id).name
        _logger.info("location_id: %s" % (location_id,))

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

        odoo_sql = "SELECT id, product_id, lot_id FROM stock_quant WHERE location_id = %s"

        self.env.cr.execute(odoo_sql, (location_id,))
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
        unaggregated = []

        for item in kardex_data:
            charge = item['Charge']
            if charge is None:
                unaggregated.append(item)  # Don't group, preserve as-is
                continue

            # Group by charge and Suchbegriff, to avoid merging unrelated products
            key = (charge, item['Suchbegriff'])

            if key not in grouped:
                grouped[key] = {
                    'Charge': charge,
                    'Suchbegriff': item['Suchbegriff'],
                    'Seriennummer': item['Seriennummer'],
                    'Bestand': 0,
                    'LocationNames': [],
                }

            grouped[key]['Bestand'] += item['Bestand']
            grouped[key]['LocationNames'].append(item['LocationName'])

        # Convert to list if needed
        kardex_data = list(grouped.values()) + unaggregated
        _logger.info("kardex_data after grouping: %s" % (kardex_data,))

            

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
            quantity = row["Bestand"]

            product_id = product_mapping.get(default_code)
            product = self.env["product.product"].search([("default_code", "=", default_code)], limit=1)
            

            if not product_id:
                continue

            lot_id = lot_mapping.get(lot_name) if lot_name else None
            # existing_kardex_quants_for_product = self.env["stock.quant"].search(
            #     [("product_id", "=", product_id), ("location_id", "=", location_id)]                
            # )
            # _logger.info(f"### existing_kardex_quants_for_product: {existing_kardex_quants_for_product}")


            if lot_id and (product_id, lot_id) in stock_quant_mapping:
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
                
                
            elif lot_name and lot_name not in lot_mapping:
                # Case 2: Create a new lot if necessary
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

