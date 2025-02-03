import logging
import re

from odoo import api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


# settings TODO: make it configurable
SEND_KARDEX_PRODUCT_ON_CREATE = False
NUMBER_OF_KARDEX_PRODUCTS_TO_GET = 5
KARDEX_DATE_HANDLING = "send"  # or 'create'


class ProductCategory(models.Model):
    _name = "product.category"
    _inherit = ["product.category"]

    kardex = fields.Boolean(string="Kardex", default=False)
    kardex_tracking = fields.Selection(
        selection=[("none", "None"), ("serial", "Serial"), ("lot", "Lot")],
        default="none",
        string="Tracking Type",
    )
    parent_id_name = fields.Char(related="parent_id.name")
    abbr = fields.Char(string="Abbreviation")


class ProductTemplate(models.Model):
    _name = "product.template"
    _inherit = ["product.template", "base.kardex.mixin"]
    _description = "Kardex PPG Data"

    product_category_ids_domain = fields.Binary(compute="_compute_category_domain")

    kardex = fields.Boolean(string="Kardex", default=False)
    kardex_id = fields.Integer(string="Kardex Id")
    kardex_product_id = fields.Integer(string="Kardex Artikel-Id")
    # kardex_product_name = fields.Char(string='Kardex Artikelbezeichnung')
    kardex_status = fields.Selection(
        selection=[("0", "Ready"), ("1", "Pending"), ("2", "Success"), ("3", "Error")],
        default="0",
        string="Kardex STATUS",
    )
    # kardex_info_1 = fields.Char(string="Kardex Info1")
    kardex_info_2 = fields.Char(string="Kardex Info2")
    kardex_info_3 = fields.Char(string="Kardex Info3")
    kardex_info_4 = fields.Char(string="Kardex Info4")
    kardex_tracking = fields.Selection(
        selection=[("none", "None"), ("serial", "Serial"), ("lot", "Lot")],
        default="none",
        string="Kardex Tracking",
    )
    # kardex_ch_verw = fields.Boolean(string="Kardex ChVerw", compute="_compute_kardex_ch_verw", store=True)
    # kardex_sn_verw = fields.Boolean(string="Kardex SnVerw", compute="_compute_kardex_sn_verw", store=True)
    # kardex_search = fields.Char(string="Kardex Suchbegriff")
    # kardex_product_group = fields.Char(string="Kardex Artikelgruppe")
    # kardex_unit = fields.Char(string="Kardex Einheit")
    kardex_row_create_time = fields.Char(string="Kardex Row_Create_Time")
    kardex_row_update_time = fields.Char(string="Kardex Row_Update_Time")
    kardex_is_fifo = fields.Boolean(string="Kardex isFIFO", default=False)
    kardex_done = fields.Boolean(string="in Kardex bekannt", default=False)

    # @api.constrains('kardex', 'default_code')
    # def _check_default_code_required(self):
    #     for record in self:
    #         if record.kardex and not record.default_code:
    #             raise ValidationError("The 'Internal Reference' (default_code) is required when 'Kardex' is enabled.")

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if "categ_id" in res:
            category = self.env["product.category"].browse(res["categ_id"])
            if category and category.kardex_tracking:
                res["tracking"] = category.kardex_tracking
                if category.kardex_tracking != 'none':
                    res["is_storable"] = True

        return res

    @api.onchange("categ_id")
    def _onchange_category_set_tracking(self):
        if self.categ_id and self.kardex:
            self.tracking = self.categ_id.kardex_tracking or "none"

    @api.onchange("categ_id")
    def _onchange_category_set_default_code(self):
        if self.categ_id and self.kardex:
            self.default_code = self.categ_id.abbr

    @api.depends("kardex")
    def _compute_category_domain(self):
        """
        Restrict the category domain to children of 'Kardex' category if 'kardex' is set to True.
        """
        for product in self:
            if product.kardex:
                kardex_categories = self.env["product.category"].search(
                    [("kardex", "=", True)]
                )
                if kardex_categories:
                    domain = [("id", "in", kardex_categories.ids)]
                else:
                    domain = []
            else:
                domain = []

            product.product_category_ids_domain = domain

    @api.constrains("default_code", "categ_id", "kardex")
    def _check_default_code_pattern(self):
        for record in self:
            if record.categ_id and record.default_code and record.kardex:
                category_abbr = re.escape(
                    record.categ_id.abbr
                )  # Escape to handle any special characters in the category name
                pattern = rf"^{category_abbr}\.[\w.]+$"  # Regex: category name + dot + alphanumeric or dots

                # Validate default_code against the pattern
                if not re.match(pattern, record.default_code):
                    raise ValidationError(
                        "The 'Internal Reference' must start with the category abbreviation, followed by a dot, and contain only alphanumeric characters or dots. "
                        f"Expected pattern: '{category_abbr}.[alphanumeric or dot]'"
                    )

    def update_to_kardex(self):
        for product in self:
            product_vals = product.read()[0]
            if self._check_already_in_kardex(product):
                product_vals["description"] = (
                    re.sub(r"<.*?>", "", product_vals["description"])
                    if product_vals["description"]
                    else ""
                )
                self._update_external_object(product_vals)
                message = "Kardex Articel was updated."
                return self._create_notification(message)
            else:
                message = "This Article is not known in Kardex."
                return self._create_notification(message)

    def send_to_kardex(self):
        for product in self:
            product_vals = product.read()[0]
            if self._check_already_in_kardex(product):
                # raise ValidationError("This product was already transfered to Kardex")
                updated = self._update_external_object(product_vals)
                if updated:
                    done = {"kardex_done": True}
                    product.write(done)
                    message = "Kardex Articel was updated."
                    return self._create_notification(message)

                raise ValidationError("Something went wrong.")

            else:
                new_article_id = self._get_kardex_article_id()
                product_vals["kardex_product_id"] = new_article_id
                # create_time, update_time = self._get_dates(product, KARDEX_DATE_HANDLING)
                # product_vals['kardex_row_create_time'] = ''
                # product_vals['kardex_row_update_time'] = ''
                (
                    product_vals["kardex_ch_verw"],
                    product_vals["kardex_sn_verw"],
                ) = self._get_sn_ch_verw(product)
                product_vals["kardex_product_group"] = self._get_product_group(product)
                product_vals["description"] = (
                    re.sub(r"<.*?>", "", product_vals["description"])
                    if product_vals["description"]
                    else ""
                )
                product_vals["kardex_unit"] = product.uom_id.name
                product_vals["kardex_search"] = product.default_code
                product_vals["kardex_status"] = "1"

                table = "PPG_Artikel"
                new_id, create_time, update_time, running_id = self._create_external_object(
                    product_vals, table
                )

                done = {
                    "kardex_done": True,
                    "kardex_id": new_id,
                    "kardex_product_id": new_article_id,
                    "kardex_row_create_time": create_time,
                    "kardex_row_update_time": update_time,
                }
                product.write(done)
                message = "Kardex Product was sent to Kardex."
                return self._create_notification(message)

    def update_status_from_kardex(self):
        for product in self:
            kardex_id = product.kardex_id
            old_status = product.kardex_status
            sql = f"SELECT STATUS, Row_Update_Time FROM PPG_Artikel WHERE ID = {kardex_id}"
            result = self._execute_query_on_mssql("select_one", sql)
            _logger.info("result: {}".format(result))
            new_status = result["STATUS"]
            update_time = result["Row_Update_Time"]

            updated = False

            if new_status != old_status and update_time:
                updated = True
                product.write(
                    {
                        "kardex_status": str(new_status),
                        "kardex_row_update_time": update_time,
                    }
                )

            if updated:
                message = f"Kardex Status was updated from {old_status} to {new_status}"
            else:
                message = "Kardex Status was not updated."

            return self._create_notification(message)

            # raise ValidationError('Something went wrong.')

    @api.model
    def sync_db(self):
        top_val = NUMBER_OF_KARDEX_PRODUCTS_TO_GET
        sql_query = f"SELECT TOP {top_val} * FROM PPG_Artikel"
        self._sync_external_db(sql_query)

    def _get_product_group(self, product):
        # group = product.categ_id.name # this is HTML object
        match = re.match(r"^[^.]+", product.default_code)

        if match:
            group = match.group(0)
            return group

        group = "NNN"
        return group

    def _get_sn_ch_verw(self, product):
        tracking = product.product_variant_ids[0].tracking
        if tracking == "lot":
            ch_verw = 1
            sn_verw = 0
        elif tracking == "serial":
            ch_verw = 0
            sn_verw = 1
        else:
            ch_verw = 0
            sn_verw = 0
        return ch_verw, sn_verw

    def _get_tracking(self, id, chverw, snverw):
        if chverw == "0" and snverw == "0":
            print("#### TRACKING FKT #####", chverw, snverw)
            result = "none"
        elif chverw == "1" and snverw == "0":
            result = "lot"
        elif chverw == "0" and snverw == "1":
            result = "serial"
        elif chverw == "1" and snverw == "1":
            raise ValidationError(
                f"Kardex ID {id}: Both CH and SN have value 1. Tracking is set to none. Please correct."
            )
            result = "none"
        return result

    def _get_categ_id(self, cat):
        parent_category = self.env["product.category"].search([("name", "=", "Kardex")])
        if not parent_category:
            parent_category = self.env["product.category"].create(
                {
                    "name": "Kardex",
                }
            )
        category = self.env["product.category"].search([("name", "=", cat)])
        if not category:
            category = self.env["product.category"].create(
                {"name": cat, "kardex": True, "parent_id": parent_category.id}
            )
        return category.id

    def _get_unit_id(self, unit_name):
        unit = self.env["uom.uom"].search([("name", "=", unit_name)])
        if not unit:
            # create category
            cat = self.env["uom.category"].search([("name", "=", "Kardex")])
            if not cat:
                cat = self.env["uom.category"].create(
                    {
                        "name": "Kardex",
                    }
                )
            unit = self.env["uom.uom"].create(
                {
                    "name": unit_name,
                    "category_id": cat.id,
                }
            )
        return unit.id

    @api.model
    def _create_record_val(self, record):
        val_dict = {}
        val_dict["name"] = record.Artikelbezeichnung
        val_dict["kardex_product_id"] = record.Artikelid
        val_dict["kardex_status"] = str(record.STATUS)
        description = record.Info1.strip() if record.Info1 else ""
        val_dict["description"] = description
        info2 = record.Info2.strip() if record.Info2 else ""
        val_dict["kardex_info_2"] = info2
        info3 = record.Info3.strip() if record.Info3 else ""
        val_dict["kardex_info_3"] = info3
        info4 = record.Info4.strip() if record.Info4 else ""
        val_dict["kardex_info_4"] = info4
        val_dict["kardex_tracking"] = self._get_tracking(
            record.ID, record.ChVerw, record.SnVerw
        )
        val_dict["default_code"] = record.Suchbegriff
        val_dict["categ_id"] = self._get_categ_id(record.Artikelgruppe.strip())
        val_dict["uom_id"] = val_dict["uom_po_id"] = self._get_unit_id(
            record.Einheit.strip()
        )
        val_dict["kardex_row_create_time"] = record.Row_Create_Time
        val_dict["kardex_row_update_time"] = record.Row_Update_Time
        val_dict["kardex_is_fifo"] = record.isFIFO
        return val_dict

    def _get_kardex_product_name(self, record):
        kardex_product_name = record["name"]
        return kardex_product_name

    def _get_kardex_article_id(self):
        # Find the current maximum kardex_prod_id
        # max_kardex_product_id = self.env['product.template'].search([('kardex_product_id', '>', '0')], order='kardex_product_id desc', limit=1).kardex_product_id

        sql_query = "SELECT Max(Artikelid) AS maximum_article_id FROM PPG_Artikel"
        res = self._execute_query_on_mssql("select_one", sql_query)
        max_kardex_product_id = res["maximum_article_id"]
        kardex_product_id = max_kardex_product_id + 1 if max_kardex_product_id else 1
        return int(kardex_product_id)

    def _get_kardex_id(self):
        sql_query = "SELECT SCOPE_IDENTITY()"
        id = self._execute_query_on_mssql("select_one", sql_query)
        return id

    def _get_kardex_status(self):
        kardex_status = "1"
        return kardex_status
        # todo: what means status exactly?

    def _update_record(self, vals, record):
        vals["kardex_status"] = self._get_kardex_status()
        # vals["kardex_product_name"] = self._get_kardex_product_name(record)

        # this should be done if product is sent to kardex
        # if not record['kardex_done'] and not vals.get('kardex_product_id', None):
        #    vals['kardex_product_id'] = self._get_kardex_article_id()

        return vals

    def _update_variants_tracking(self, tracking_value):
        for product in self:
            for variant in product.product_variant_ids:
                variant.write({"tracking": tracking_value})

    @api.model
    def create(self, vals):
        record = super(ProductTemplate, self).create(vals)
        # handle tracking
        if "kardex_tracking" in vals:
            record._update_variants_tracking(vals["kardex_tracking"])
        # fixing missing kardex values
        if vals["kardex"]:
            vals = self._update_record(vals, record)
            # vals['kardex_row_create_time'], vals['kardex_row_update_time'] = self._get_dates(record, KARDEX_DATE_HANDLING)

            if (
                not (record.kardex_done or vals["kardex_done"])
                and SEND_KARDEX_PRODUCT_ON_CREATE
            ):
                table = "PPG_Artikel"
                new_id = self._create_external_object(
                    vals, table
                )  # in case of creating a new record the new id is returned
                vals["kardex_done"] = True
                vals["kardex_id"] = new_id

            _logger.info("VALS %s" % (vals,))
            record.write(vals)

        return record
        # TODO:
        # tracking -> ChVerw, SnVerw
        # product.product !

    @api.model
    def write(self, vals):
        """
        if a kardex product has been changed the kardex_done flag is set to False
        """
        # if vals:
        #     for record in self:
        #         if record.kardex and record.kardex_done:
        #             #not_done = {'kardex_done': False }
        #             #record.write(not_done)
        #             vals['kardex_done'] = False

        return super(ProductTemplate, self).write(vals)
