
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import datetime
import pytz

import logging


_logger = logging.getLogger(__name__)


class SaleOrderInherit(models.Model):
    _inherit = "sale.order"


    x_economic_activity_id = fields.Many2one("xeconomic.activity", string="Actividad Económica", required=False,
                                             context={'active_test': True}, )

    def _prepare_invoice(self):
        vals = super(SaleOrderInherit, self)._prepare_invoice()
        if vals:
            vals['x_economic_activity_id'] = self.x_economic_activity_id
            vals['x_document_type'] = 'FE'
        return vals 

    @api.onchange('partner_id', 'company_id')
    def _get_economic_activities(self):
        for rec in self:
            rec.x_economic_activity_id = rec.company_id.x_economic_activity_id