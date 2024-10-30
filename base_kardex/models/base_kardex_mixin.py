import logging
from datetime import datetime
from types import SimpleNamespace

from odoo import _, api, fields, models
from odoo.tools import pytz
from odoo.exceptions import ValidationError


_logger = logging.getLogger(__name__)

ODOO_KARDEX_PRODUCT_FIXER = {
    'kardex_product_id': 'Artikelid',
    'name': 'Artikelbezeichnung',
    'kardex_status': 'STATUS',
    'description': 'Info1',
    'kardex_info_2': 'Info2',
    'kardex_info_3': 'Info3',
    'kardex_info_4': 'Info4',
    'kardex_ch_verw': 'ChVerw',
    'kardex_sn_verw': 'SnVerw',
    'kardex_search': 'Suchbegriff',
    'kardex_product_group': 'Artikelgruppe',
    'kardex_unit': 'Einheit',
    #'kardex_row_create_time': 'Row_Create_Time',
    #'kardex_row_update_time': 'Row_Update_Time',
    'kardex_is_fifo': 'isFIFO'
}


ODOO_KARDEX_PICKING_FIXER = {
    'kardex_product_id': 'ArtikelID',
    #'kardex_row_create_time': 'Row_Create_Time',
    #'kardex_row_update_time': 'Row_Update_Time',
    'kardex_status': 'Status',
    'kardex_unit': 'Einheit',
    'kardex_quantity': 'Menge',
}





class BaseKardexMixin(models.AbstractModel):
    _name = 'base.kardex.mixin'
    _description = 'Base Kardex Mixin'

    def _create_notification(self, message):
        notification_dict = {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Kardex Message",
                "message": message,
                "sticky": False,
                'next': {
                    'type': 'ir.actions.act_window_close',
                }
            },
        }
        return notification_dict


    def _convert_date(self, date_obj):    
        
        formatted_date_str = date_obj.strftime('%b %e %Y %l:%M')

        # workaround for not working %p conversion of datetime library used in odoo (?)
        if date_obj.hour < 12:
            am_pm = 'AM'
        else:
            am_pm = 'PM'

        formatted_date_str += am_pm
        return formatted_date_str

    def _fix_dictionary(self, fixer, dict):
        return { fixer.get(k, k): v for k, v in dict.items() if k in fixer.keys() }

    def _replace_false_with_empty_string(self, dict):
        return {k: '' if v is False else v for k, v in dict.items()}

    def _execute_query_on_mssql(self, query_type, query, *params):
        # Find the instance of base.external.mssql with priority=True
        mssql_instance = self.env['base.external.mssql'].search([('priority', '=', True)], limit=1)
        if mssql_instance:
            # Call the execute method on the found instance
            result = mssql_instance.execute(query_type, query, *params)
            # _logger.info("result: %s" % (result,))
            return result
        else:
            raise ValidationError("No active MSSQL instance found with priority=True")

    def _check_already_in_kardex(self, record):
        #if product.kardex_done:
        #    return True
        _logger.info("record._name: %s" % (record._name,))
        sql_query = f"SELECT ID, Artikelbezeichnung FROM PPG_Artikel WHERE ID={record.kardex_id}"  
        rows = self._execute_query_on_mssql('select', sql_query)
        if len(rows) > 0:
            return True

    def _update_external_object(self, vals):
        # translate vals dictionary to external database scheme
        fixer = ODOO_KARDEX_PRODUCT_FIXER
        kardex_dict = self._replace_false_with_empty_string(self._fix_dictionary(fixer, vals))
        # building list 
        kardex_list = []
        for key,value in kardex_dict.items():
            if type(value) is int: # Handle Integers
                kardex_list.append(f"{key} = {value}")
            else: # Default Handler
                kardex_list.append(f"{key} = '{value}'")
            # generate string from key-value-pair list
        data = ", ".join(kardex_list)
        # building sql query
        table = 'PPG_Artikel'
        id = vals.get('kardex_product_id', None)
        if id:
            sql = f"UPDATE {table} SET {data} WHERE Artikelid = {id}"
            self._execute_query_on_mssql('update', sql)
            return True
        
        raise ValidationError("The data contains no Kardex Article Id.")
        return False

    def _get_dates(self, record, date_handling):
        if date_handling == 'create':
            create_date_utc = record.create_date
        elif date_handling == 'send':
            create_date_utc = datetime.now()

        user_tz = pytz.timezone(self.env.context.get('tz') or self.env.user.tz)
        create_date_local = pytz.utc.localize(create_date_utc).astimezone(user_tz)
        create_time = update_time = self._convert_date(create_date_local)

        return create_time, update_time


    def _create_external_object(self, vals, table):
        # translate vals dictionary to external database scheme
        if table == "PPG_Artikel":
            fixer = ODOO_KARDEX_PRODUCT_FIXER
        elif table == "PPG_Auftraege":
            fixer = ODOO_KARDEX_PICKING_FIXER
        kardex_dict = self._replace_false_with_empty_string(self._fix_dictionary(fixer, vals))
        # building sql query
        placeholders = ', '.join(['?'] * len(kardex_dict))
        columns = ', '.join(kardex_dict.keys())
        sql = f"INSERT INTO {table} ({columns}) VALUES {tuple(kardex_dict.values())}"
        _logger.info('sql: %s' % (sql,))
        new_id = self._execute_query_on_mssql('insert', sql)
        # in case of inserting a record result is id of created object
        # getting dates from external database
        columns = 'Row_Create_Time, Row_Update_Time'
        sql = f"SELECT {columns} FROM {table} WHERE ID = {new_id}"
        _logger.info('sql: %s' % (sql,))
        record = self._execute_query_on_mssql('select', sql)
        _logger.info('record: %s' % (record,))
        if len(record) == 1:
            create_time = record[0]["Row_Create_Time"]
            update_time = record[0]["Row_Update_Time"]
        return new_id, create_time, update_time

    def _sync_external_db(self, query):
        # import pdb; pdb.set_trace()

        # Execute the query using the external MSSQL instance
        records = self._execute_query_on_mssql('select', query)
        # _logger.info('RECORDS: %s' % (records,))
        
        if records:
            # records is a list of dictionaries/tuples with keys similar to kardex model
            for record in records:
                _logger.info('RECORD: %s' % (record,))
                record = SimpleNamespace(**record)
                existing_product = self.search([('kardex_id', '=', record.ID)], limit=1)
                
                val_dict = self._create_record_val(record)
                if existing_product:
                    # Update the existing record
                    existing_product.write(val_dict)
                else:
                    # because product comes from kardex kardex and kardex_done is set to true
                    val_dict['kardex_done'] = True
                    val_dict['kardex'] = True
                    val_dict['kardex_id'] = record.ID
                    val_dict['kardex_product_id'] = record.Artikelid
                    self.create(val_dict)
        else:
            raise ValidationError("No Records found in external Database")

