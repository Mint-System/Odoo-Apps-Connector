# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class StockLocation(models.Model):
    _inherit = "stock.location"

    kardex = fields.Boolean(
        "Kardex Location",
        default=False,
        help="The one location that identifies the Kardex to the picking flow (send_to_kardex, "
        "sync_stocks, ...). At most one location may be flagged.",
    )

    @api.constrains("kardex")
    def _check_kardex_unique(self):
        if self.env["stock.location"].search_count([("kardex", "=", True)]) > 1:
            raise ValidationError(_("Only one location may be flagged as the Kardex location."))
