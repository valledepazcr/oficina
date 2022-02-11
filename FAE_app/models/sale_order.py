
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
            if self.partner_id.x_foreign_partner:
                document_type = 'FEE'
            elif self.partner_id.vat:
                if ((self.partner_id.country_id and self.partner_id.country_id.code != 'CR')
                    or (self.partner_id.x_identification_type_id and self.partner_id.x_identification_type_id.code == '05')):
                    document_type = 'TE'
                else:
                    document_type = 'FE'
            else:
                document_type = 'TE'
            vals['x_economic_activity_id'] = self.x_economic_activity_id
            vals['x_document_type'] = document_type
        return vals 

    @api.onchange('partner_id', 'company_id')
    def _get_economic_activities(self):
        for rec in self:
            rec.x_economic_activity_id = rec.company_id.x_economic_activity_id