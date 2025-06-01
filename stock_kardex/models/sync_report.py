from odoo import fields, models


class KardexSyncReport(models.Model):
    _name = "kardex.sync.report"
    _description = "Kardex Sync Report"
    _order = "create_date desc"

    name = fields.Char(string="Sync Name", required=True)
    synced_by = fields.Many2one("res.users", string="User", default=lambda self: self.env.user)
    sync_time = fields.Datetime(string="Sync Time", default=fields.Datetime.now)
    product_count = fields.Integer(compute="_compute_product_count")
    details = fields.Text(string="Details")
    line_ids = fields.One2many("kardex.sync.report.line", "report_id", string="Sync Lines")

    def _compute_product_count(self):
        for rec in self:
            rec.product_count = len(rec.line_ids)


class KardexSyncReportLine(models.Model):
    _name = "kardex.sync.report.line"
    _description = "Kardex Sync Report Line"

    report_id = fields.Many2one("kardex.sync.report", string="Sync Report", ondelete="cascade")
    product_id = fields.Many2one("product.product", required=True)
    default_code = fields.Char(related="product_id.default_code", store=True)
    # name = fields.Char(related='product_id.name', store=True)
    changes = fields.Text(string="Changes")
