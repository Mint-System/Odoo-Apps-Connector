import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class KubectlContext(models.Model):
    _name = "kubectl.context"
    _description = "Kubectl Context"

    name = fields.Char()
    cluster_id = fields.Many2one("kubectl.cluster")
    config = fields.Text("config")
    is_current = fields.Boolean(compute="_compute_is_current")

    def _compute_is_current(self):
        for rec in self:
            rec.is_current = self.env.user.current_context_id == rec

    def action_use_context(self):
        self.ensure_one()
        self.env.user.current_context_id = self
