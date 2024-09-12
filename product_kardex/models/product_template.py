import logging

from odoo import _, api, fields, models
from odoo.tools import pytz
from odoo.exceptions import UserError, ValidationError


_logger = logging.getLogger(__name__)


from datetime import datetime

# settings TODO: make it configurable
SEND_KARDEX_PRODUCT_ON_CREATE=True


class ProductTemplate(models.Model):
    _name = 'product.template'
    _inherit = ['product.template', 'base.kardex.mixin']
    _description = 'Kardex PPG Data'
    
    kardex = fields.Boolean(string='Kardex', default=False)
    kardex_product_id = fields.Integer(string='Kardex Artikelid')
    kardex_product_name = fields.Char(string='Kardex Artikelbezeichnung')
    kardex_status = fields.Integer(string="Kardex STATUS")
    kardex_info_1 = fields.Char(string="Kardex Info1")
    kardex_info_2 = fields.Char(string="Kardex Info2")
    kardex_info_3 = fields.Char(string="Kardex Info3")
    kardex_info_4 = fields.Char(string="Kardex Info4")
    kardex_ch_verw = fields.Char(string="Kardex ChVerw")
    kardex_sn_verw = fields.Char(string="Kardex SnVerw")
    kardex_search = fields.Char(string="Kardex Suchbegriff")
    kardex_product_group = fields.Char(string="Kardex Artikelgruppe")
    kardex_unit = fields.Char(string="Kardex Einheit")
    kardex_row_create_time = fields.Char(string="Kardex Row_Create_Time")
    kardex_row_update_time = fields.Char(string="Kardex Row_Update_Time")
    kardex_is_fifo = fields.Char(string="Kardex isFIFO")
    kardex_done = fields.Boolean(string="in Kardex bekannt", default=False)

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


    def send_to_kardex(self):
        
        for product in self:
            product_vals = product.read()[0]
            if self._check_already_in_kardex(product):
                #raise ValidationError("This product was already transfered to Kardex")
                updated = self._update_external_object(product_vals)
                if updated:
                    done = {'kardex_done': True }
                    product.write(done)
                    message = 'Kardex Articel was updated.'
                    return self._create_notification(message) 

                raise ValidationError('Something went wrong.')

            else:
                self._create_external_object(product_vals)
                done = {'kardex_done': True }
                product.write(done)
                message = 'Kardex Product was created'
                return self._create_notification(message)


    def sync_db(self):
        top_val = 20
        sql_query = f"SELECT TOP {top_val} * FROM PPG_Artikel"
        self._sync_external_db(sql_query)


    @api.model
    def _create_record_val(self, record):
        val_dict = {}
        val_dict["name"] = record.Artikelbezeichnung  
        val_dict["kardex_product_id"] = record.Artikelid
        val_dict["kardex_product_name"] = record.Artikelbezeichnung
        val_dict["kardex_info_1"] = record.Info1
        val_dict["kardex_info_2"] = record.Info2
        val_dict["kardex_info_3"] = record.Info3
        val_dict["kardex_info_4"] = record.Info4
        val_dict["kardex_ch_verw"]= record.ChVerw
        val_dict["kardex_sn_verw"] = record.SnVerw
        val_dict["kardex_search"] = record.Suchbegriff
        val_dict["kardex_product_group"] = record.Artikelgruppe
        val_dict["kardex_unit"] = record.Einheit
        val_dict["kardex_row_create_time"] = record.Row_Create_Time
        val_dict["kardex_row_update_time"] = record.Row_Update_Time
        val_dict["kardex_is_fifo"] = record.isFIFO
        return val_dict

    
    def _get_kardex_product_name(self, record):
        # kardex_product_name = vals['name']
        kardex_product_name = record['name']
        return kardex_product_name

    def _get_kardex_article_id(self):
        # Find the current maximum kardex_prod_id
        max_kardex_product_id = self.env['product.template'].search([('kardex_product_id', '>', '0')], order='kardex_product_id desc', limit=1).kardex_product_id
        kardex_product_id = max_kardex_product_id + 1 if max_kardex_product_id else 1
        return kardex_product_id

    def _get_kardex_status(self):
        kardex_status = 2
        return kardex_status
        # todo: what means status exactly?

    def _update_record(self, vals, record):
        
        # vals['kardex_status'] = self._get_kardex_status()
        # vals['kardex_product_name'] = self._get_kardex_product_name(vals)
        
        # if not vals['kardex_done']: 
        #     vals['kardex_product_id'] = self._get_kardex_article_id()

        # # fixing kardex date strings from record.create_date
        # # 1. get create date in UTC
        # create_date_utc = record.create_date
        # # 2. get tz
        # user_tz = pytz.timezone(self.env.context.get('tz') or self.env.user.tz)
        # # 3. create local date
        # create_date_local = pytz.utc.localize(create_date_utc).astimezone(user_tz)
        # # 4. convert local date to desired kardex date string
        # vals['kardex_row_create_time'] = vals['kardex_row_update_time'] = _convert_date(create_date_local)
        # # 5. update record

        # return vals

        vals["kardex_status"] = self._get_kardex_status()
        vals["kardex_product_name"] = self._get_kardex_product_name(record)
        
        if not record['kardex_done']: 
            vals['kardex_product_id'] = self._get_kardex_article_id()
        
        # fixing kardex date strings from record.create_date
        # 1. get create date in UTC
        create_date_utc = record.create_date
        # 2. get tz
        user_tz = pytz.timezone(self.env.context.get('tz') or self.env.user.tz)
        # 3. create local date
        create_date_local = pytz.utc.localize(create_date_utc).astimezone(user_tz)
        # 4. convert local date to desired kardex date string
        vals['kardex_row_create_time'] = vals['kardex_row_update_time'] = _convert_date(create_date_local)
        # 5. update record

        return vals



    @api.model
    def create(self, vals):
        # we first need a record
        record = super(ProductTemplate, self).create(vals)

        # fixing missing kardex values
        if vals['kardex']:
            vals = self._update_record(vals, record)

            if not record.kardex_done and SEND_KARDEX_PRODUCT_ON_CREATE:
                _external_created = self._create_external_object(vals)
                vals['kardex_done'] = True
           
            record.write(vals)

        return record
        # TODO:
        # tracking -> ChVerw, SnVerw
        # product.product !

    @api.model
    def write(self, vals):
        _logger.info('write called with self= %s' % (self,))
        """
        if a kardex product has been changed the kardex_done flag is set to False
        """
        if vals:
            for record in self:
                if record.kardex and record.kardex_done:
                    #not_done = {'kardex_done': False }
                    #record.write(not_done)
                    vals['kardex_done'] = False

        return super(ProductTemplate, self).write(vals)
        

        




        
