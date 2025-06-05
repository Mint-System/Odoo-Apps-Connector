import logging
from datetime import datetime
from types import SimpleNamespace

import pytz

from odoo import _, models
from odoo.exceptions import ValidationError

# from odoo.tools import pytz

_logger = logging.getLogger(__name__)

ODOO_KARDEX_PRODUCT_FIXER = {
    "kardex_product_id": "Artikelid",
    "name": "Artikelbezeichnung",
    "kardex_status": "STATUS",
    "description": "Info1",
    "kardex_info_2": "Info2",
    "kardex_info_3": "Info3",
    "kardex_info_4": "Info4",
    "kardex_ch_verw": "ChVerw",
    "kardex_sn_verw": "SnVerw",
    "kardex_search": "Suchbegriff",
    "default_code": "Suchbegriff",
    "kardex_search_term_one": "Info1",
    "kardex_search_term_two": "Info2",
    "kardex_product_group": "Artikelgruppe",
    "kardex_unit": "Einheit",
    #'kardex_row_create_time': 'Row_Create_Time',
    #'kardex_row_update_time': 'Row_Update_Time',
    "kardex_is_fifo": "isFIFO",
}


ODOO_KARDEX_PICKING_FIXER = {
    "kardex_product_id": "ArtikelID",
    #'kardex_row_create_time': 'Row_Create_Time',
    #'kardex_row_update_time': 'Row_Update_Time',
    "kardex_status": "Status",
    "kardex_unit": "Einheit",
    "kardex_quantity": "Menge",
    "kardex_doc_number": "Belegnummer",
    "kardex_direction": "Richtung",
    "kardex_search": "Suchbegriff",
    "kardex_running_id": "BzId",
    "kardex_send_flag": "Versandflag",
    "kardex_charge": "Charge",
    "kardex_serial": "Seriennummer",
}


class BaseKardexMixin(models.AbstractModel):
    _name = "base.kardex.mixin"
    _description = "Base Kardex Mixin"

    def _create_notification(self, message):
        notification_dict = {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Kardex Message",
                "message": message,
                "sticky": False,
                "next": {
                    "type": "ir.actions.act_window_close",
                },
            },
        }
        return notification_dict

    def _convert_date(self, date_obj):
        formatted_date_str = date_obj.strftime("%b %e %Y %l:%M")

        # workaround for not working %p conversion of datetime library used in odoo (?)
        if date_obj.hour < 12:
            am_pm = "AM"
        else:
            am_pm = "PM"

        formatted_date_str += am_pm
        return formatted_date_str

    def _fix_dictionary(self, fixer, dict):
        return {fixer.get(k, k): v for k, v in dict.items() if k in fixer.keys()}

    def _replace_false_with_empty_string(self, dict):
        return {k: "" if v is False else v for k, v in dict.items()}

    def _execute_query_on_mssql(self, query_type, query, *params):
        # Find the instance of base.external.mssql with priority=True
        mssql_instance = self.env["base.external.mssql"].search([("priority", "=", True)], limit=1)
        if mssql_instance:
            # Call the execute method on the found instance
            result = mssql_instance.execute(query_type, query, *params)

            return result
        else:
            raise ValidationError(_("No active MSSQL instance found with priority=True"))

    def _execute_query_on_proddb(self, default_code=None, products=None):
        if default_code:
            params = ([default_code],)
        elif products:
            params = (tuple(products.keys()),)
        else:
            raise ValidationError(_("No products provided"))

        proddb_instance = self.env["base.external.mssql"].search([("name", "=", "proddb")], limit=1)

        if not proddb_instance:
            raise ValidationError(_("No active SQL instance found with name 'proddb'"))

        query_material = """
        SELECT
           MaterialName
        FROM
           Materialbase
        WHERE MaterialName IN %s
        """
        result_material = proddb_instance.execute("select", query_material, params)

        query = """
        SELECT
            Materialbase.MaterialName as Produktnr,
            LocContentbreakdown.QuantityCurrent,
            LocContentbreakdown.Serialnumber,
            LocContentbreakdown.Lot,
            Location.LocationName
        FROM
            LocContentbreakdown
            LEFT JOIN LocContent on LocContentbreakdown.LocContentId = LocContent.LocContentId
            LEFT JOIN Materialbase on LocContent.MaterialId = MaterialBase.MaterialId
            LEFT JOIN Location on LocContent.LocationId = Location.LocationId
        WHERE Materialbase.MaterialName IN %s
            """

        result = proddb_instance.execute("select", query, params)
        return result_material, result

    def _check_already_in_kardex(self, record):
        sql_query = f"SELECT ID, Suchbegriff FROM PPG_Artikel WHERE Suchbegriff='{record.default_code}'"
        rows = self._execute_query_on_mssql("select", sql_query)
        if len(rows) > 0:
            return True

    def _read_external_object_from_proddb(self, default_code=None, products=None):
        rows_material, rows = self._execute_query_on_proddb(default_code, products)
        return rows_material, rows

    def _update_external_object(self, vals):
        table = "PPG_Artikel"
        default_code = vals.pop("default_code", None)
        # translate vals dictionary to external database scheme
        if default_code:
            fixer = ODOO_KARDEX_PRODUCT_FIXER
            kardex_dict = self._replace_false_with_empty_string(self._fix_dictionary(fixer, vals))
            # building list
            kardex_list = []
            for key, value in kardex_dict.items():
                if type(value) is int:  # Handle Integers
                    kardex_list.append(f"{key} = {value}")
                else:  # Default Handler
                    kardex_list.append(f"{key} = '{value}'")
                # generate string from key-value-pair list
            data = ", ".join(kardex_list)
            # building sql query

            sql = f"UPDATE {table} SET {data} WHERE Suchbegriff = '{default_code}'"
            self._execute_query_on_mssql("update", sql)
            return True

        raise ValidationError(_("The data contains no default code."))

    def _get_dates(self, record, date_handling):
        if date_handling == "create":
            create_date_utc = record.create_date
        elif date_handling == "send":
            create_date_utc = datetime.now()

        user_tz = pytz.timezone(self.env.context.get("tz") or self.env.user.tz)
        create_date_local = pytz.utc.localize(create_date_utc).astimezone(user_tz)
        create_time = update_time = self._convert_date(create_date_local)

        return create_time, update_time

    def _create_external_object(self, vals, table):
        # translate vals dictionary to external database scheme
        # if table == "PPG_Artikel":
        #     fixer = ODOO_KARDEX_PRODUCT_FIXER
        # elif table == "PPG_Auftraege":
        #     fixer = ODOO_KARDEX_PICKING_FIXER
        # kardex_dict = self._replace_false_with_empty_string(self._fix_dictionary(fixer, vals))
        # # building sql query
        # ", ".join(["?"] * len(kardex_dict))
        # columns = ", ".join(kardex_dict.keys())
        # sql = f"INSERT INTO {table} ({columns}) VALUES {tuple(kardex_dict.values())}"

        # get the db driver

        sqldb = self.env["base.external.mssql"].search([("priority", "=", True)], limit=1)
        db_driver = sqldb._get_db_driver()
        # _logger.info("Database driver: %s", db_driver)

        # Pick the fixer based on table
        if table == "PPG_Artikel":
            fixer = ODOO_KARDEX_PRODUCT_FIXER
        elif table == "PPG_Auftraege":
            fixer = ODOO_KARDEX_PICKING_FIXER
        else:
            raise ValueError(f"Unsupported table: {table}")

        # Clean and prepare dictionary
        kardex_dict = self._replace_false_with_empty_string(self._fix_dictionary(fixer, vals))

        # Extract columns and values
        columns = ", ".join(kardex_dict.keys())
        if db_driver == "pymssql":
            placeholders = ", ".join(["%s"] * len(kardex_dict))
        elif db_driver == "pyodbc":
            placeholders = ", ".join(["?"] * len(kardex_dict))
        values = tuple(kardex_dict.values())

        # Construct SQL safely
        sql = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"

        new_id = self._execute_query_on_mssql("insert", sql, values)
        # in case of inserting a record result is id of created object
        # getting dates from external database
        columns = "Row_Create_Time, Row_Update_Time"
        if table == "PPG_Auftraege":
            columns = f"{columns}, BzId"

        sql = f"SELECT {columns} FROM {table} WHERE ID = {new_id}"
        record = self._execute_query_on_mssql("select", sql)

        running_id = ""
        if len(record) == 1:
            create_time = record[0]["Row_Create_Time"]
            update_time = record[0]["Row_Update_Time"]
            if table == "PPG_Auftraege":
                running_id = record[0]["BzId"]
        return new_id, create_time, update_time, running_id

    def _sync_external_db(self, query):
        # import pdb; pdb.set_trace()

        # Execute the query using the external MSSQL instance
        records = self._execute_query_on_mssql("select", query)

        if records:
            # records is a list of dictionaries/tuples with keys similar to kardex model
            for record in records:
                record = SimpleNamespace(**record)
                existing_product = self.search([("kardex_id", "=", record.ID)], limit=1)

                val_dict = self._create_record_val(record)
                if existing_product:
                    # Update the existing record
                    existing_product.write(val_dict)
                else:
                    # because product comes from kardex kardex and kardex_done is set to true
                    val_dict["kardex_done"] = True
                    val_dict["kardex"] = True
                    val_dict["kardex_id"] = record.ID
                    val_dict["kardex_product_id"] = record.Artikelid
                    self.create(val_dict)
        else:
            raise ValidationError(_("No Records found in external Database"))

    # def _get_destination_location_for_product(self, product):
    #     """Determine the appropriate destination location for a product."""
    #     if not product:
    #         return False

    #     # First preference: product's last_location_id
    #     location = product.last_location_id
    #     if location:
    #         return location

    #     # Second: last location with quantity > 0
    #     quant = self.env['stock.quant'].search([
    #         ('product_id', '=', product.id),
    #         ('quantity', '>', 0)
    #     ], order='write_date desc', limit=1)

    #     return quant.location_id if quant else False
