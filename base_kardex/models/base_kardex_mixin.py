import logging

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


_logger = logging.getLogger(__name__)

ODOO_KARDEX_PRODUCT_FIXER = {
    'kardex_product_id': 'Artikelid',
    'kardex_product_name': 'Artikelbezeichnung',
    'kardex_status': 'STATUS',
    'kardex_info_1': 'Info1',
    'kardex_info_2': 'Info2',
    'kardex_info_3': 'Info3',
    'kardex_info_4': 'Info4',
    'kardex_ch_verw': 'ChVerw',
    'kardex_sn_verw': 'SnVerw',
    'kardex_search': 'Suchbegriff',
    'kardex_product_group': 'Artikelgruppe',
    'kardex_unit': 'Einheit',
    'kardex_row_create_time': 'Row_Create_Time',
    'kardex_row_update_time': 'Row_Update_Time',
    'kardex_is_fifo': 'isFIFO'
}


def _convert_date(date_obj):    
        
    formatted_date_str = date_obj.strftime('%b %e %Y %l:%M')

    # workaround for not working %p conversion of datetime library used in odoo (?)
    if date_obj.hour < 12:
        am_pm = 'AM'
    else:
        am_pm = 'PM'

    formatted_date_str += am_pm
    return formatted_date_str

def _fix_dictionary(fixer, dict):
    return { fixer.get(k, k): v for k, v in dict.items() if k in fixer.keys() }

def _replace_false_with_empty_string(dict):
    return {k: '' if v is False else v for k, v in dict.items()}


class BaseKardexMixin(models.AbstractModel):
    _name = 'base.kardex.mixin'
    _description = 'Base Kardex Mixin'

    def _execute_query_on_mssql(self, query_type, query, *params):
        # Find the instance of base.external.mssql with priority=True
        mssql_instance = self.env['base.external.mssql'].search([('priority', '=', True)], limit=1)
        if mssql_instance:
            # Call the execute method on the found instance
            _logger.info("query: %s" % (query,))
            result = mssql_instance.execute(query_type, query, *params)
            return result
        else:
            raise ValidationError("No active MSSQL instance found with priority=True")

    def _check_already_in_kardex(self, record):
        #if product.kardex_done:
        #    return True
        _logger.info("record._name: %s" % (record._name,))
        sql_query = f"SELECT Artikelid, Artikelbezeichnung FROM PPG_Artikel WHERE Artikelid={record.kardex_product_id}"  
        rows = self._execute_query_on_mssql('select', sql_query)
        if len(rows) > 0:
            return True

    def _update_external_object(self, vals):
        # translate vals dictionary to external database scheme
        fixer = ODOO_KARDEX_PRODUCT_FIXER
        kardex_dict = _replace_false_with_empty_string(_fix_dictionary(fixer, vals))
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
            print('sql:', sql)
            self._execute_query_on_mssql('update', sql)
            return True
        
        raise ValidationError("The data contains no Kardex Article Id.")
        return False

    def _create_external_object(self, vals):
        # translate vals dictionary to external database scheme
        fixer = ODOO_KARDEX_PRODUCT_FIXER
        kardex_dict = _replace_false_with_empty_string(_fix_dictionary(fixer, vals))
        # building sql query
        placeholders = ', '.join(['?'] * len(kardex_dict))
        columns = ', '.join(kardex_dict.keys())
        table = 'PPG_Artikel'
        sql = f"INSERT INTO {table} ({columns}) VALUES {tuple(kardex_dict.values())}"
        _logger.info('sql: %s' % (sql,))
        self._execute_query_on_mssql('insert', sql)

    def _sync_external_db(self, query):

        # Execute the query using the external MSSQL instance
        records = self._execute_query_on_mssql('select', query)
        
        if records:
            # records is a list of dictionaries/tuples with keys similar to kardex model
            for record in records:
                _logger.info('record: %s' % (record,))
                existing_product = self.search([('kardex_product_id', '=', record.Artikelid)], limit=1)
                
                val_dict = self._create_record_val(record)
                if existing_product:
                    # Update the existing record
                    existing_product.write(val_dict)
                else:
                    # because product comes from kardex kardex and kardex_done is set to true
                    val_dict['kardex_done'] = True
                    val_dict['kardex'] = True
                    self.create(val_dict)
        else:
            raise ValidationError("No Records found in external Database")

