import logging
from datetime import datetime
from types import SimpleNamespace

import pytz

from odoo import _, api, models
from odoo.exceptions import ValidationError

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
    "kardex_is_fifo": "isFIFO",
}


ODOO_KARDEX_PICKING_FIXER = {
    "kardex_product_id": "ArtikelID",
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

    @api.model
    def _get_sdb(self):
        """The interface data source (SchnittstellenDB) in use."""
        return self.env["base.external.mssql"]._get_by_database_type("interface")

    @api.model
    def _get_proddb(self):
        """The ProdDB data source in use."""
        return self.env["base.external.mssql"]._get_by_database_type("proddb")

    def _execute_query_on_mssql(self, query_type, query, *params):
        mssql_instance = self._get_sdb()
        if not mssql_instance:
            raise ValidationError(_("No interface data source is used."))
        return mssql_instance.execute(query_type, query, *params)

    def _check_proddb(self):
        connected = False
        proddb_instance = self._get_proddb()
        if proddb_instance:
            try:
                with proddb_instance.connection_open():
                    connected = True
            except Exception as e:
                _logger.warning("Proddb DB connection failed: %s", e)
        self.env["ir.config_parameter"].sudo().set_param("base_kardex.proddb_connected", str(connected))

    @api.model
    def _check_kardex(self):
        connected = False
        kardexdb_instance = self._get_sdb()
        if kardexdb_instance:
            try:
                with kardexdb_instance.connection_open():
                    connected = True
            except Exception as e:
                _logger.warning("Kardex DB connection failed: %s", e)
        self.env["ir.config_parameter"].sudo().set_param("base_kardex.ext_db_connected", str(connected))

    def _execute_query_on_proddb(self, default_code=None, products=None):
        if default_code:
            params = ([default_code],)
        elif products:
            params = (tuple(products.keys()),)
        else:
            raise ValidationError(_("No products provided"))

        proddb_instance = self._get_proddb()
        if not proddb_instance:
            raise ValidationError(_("No ProdDB data source is used."))

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

    def _sql_placeholder(self):
        """Parameter placeholder of the driver of the active SDB connection."""
        driver = self._get_sdb()._get_db_driver()
        return "?" if driver == "pyodbc" else "%s"

    def _check_already_in_kardex(self, record):
        rows = self._execute_query_on_mssql(
            "select",
            f"SELECT ID, Suchbegriff FROM PPG_Artikel WHERE Suchbegriff = {self._sql_placeholder()}",
            (record.default_code,),
        )
        return len(rows) > 0

    def _read_external_object_from_proddb(self, default_code=None, products=None):
        rows_material, rows = self._execute_query_on_proddb(default_code, products)
        return rows_material, rows

    def _update_external_object(self, vals):
        table = "PPG_Artikel"
        default_code = vals.pop("default_code", None)
        if not default_code:
            raise ValidationError(_("The data contains no default code."))

        kardex_dict = self._replace_false_with_empty_string(self._fix_dictionary(ODOO_KARDEX_PRODUCT_FIXER, vals))
        placeholder = self._sql_placeholder()
        assignments = ", ".join(f"{column} = {placeholder}" for column in kardex_dict)
        sql = f"UPDATE {table} SET {assignments} WHERE Suchbegriff = {placeholder}"
        self._execute_query_on_mssql("update", sql, (*kardex_dict.values(), default_code))
        return True

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
        """Insert a row into PPG_Artikel or PPG_Auftraege.

        Returns ``(new_id, create_time, update_time, running_id)``; the timestamps
        and the BzId are read back because the SDB sets them itself.
        """
        fixers = {"PPG_Artikel": ODOO_KARDEX_PRODUCT_FIXER, "PPG_Auftraege": ODOO_KARDEX_PICKING_FIXER}
        if table not in fixers:
            raise ValueError(f"Unsupported table: {table}")

        kardex_dict = self._replace_false_with_empty_string(self._fix_dictionary(fixers[table], vals))
        placeholders = ", ".join([self._sql_placeholder()] * len(kardex_dict))
        sql = f"INSERT INTO {table} ({', '.join(kardex_dict)}) VALUES ({placeholders})"
        new_id = self._execute_query_on_mssql("insert", sql, tuple(kardex_dict.values()))

        columns = "Row_Create_Time, Row_Update_Time"
        if table == "PPG_Auftraege":
            columns += ", BzId"
        record = self._execute_query_on_mssql("select", f"SELECT {columns} FROM {table} WHERE ID = {int(new_id)}")

        create_time = update_time = None
        running_id = ""
        if len(record) == 1:
            create_time = record[0]["Row_Create_Time"]
            update_time = record[0]["Row_Update_Time"]
            if table == "PPG_Auftraege":
                running_id = record[0]["BzId"]
        return new_id, create_time, update_time, running_id

    def _sync_external_db(self, query):
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
                    # product comes from Kardex, so it is already known there;
                    # "kardex" itself is derived from the category/location, not set here
                    val_dict["kardex_done"] = True
                    val_dict["kardex_id"] = record.ID
                    val_dict["kardex_product_id"] = record.Artikelid
                    self.create(val_dict)
        else:
            raise ValidationError(_("No Records found in external Database"))

    @api.model
    def _is_kardex_db_connected(self):
        val = self.env["ir.config_parameter"].sudo().get_param("base_kardex.ext_db_connected", default="False")
        return val == "True"

    @api.model
    def _is_proddb_connected(self):
        val = self.env["ir.config_parameter"].sudo().get_param("base_kardex.proddb_connected", default="False")
        return val == "True"
