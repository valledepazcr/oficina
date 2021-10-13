import datetime
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging
_logger = logging.getLogger(__name__)



class xTaxCode(models.Model):
    _name = "xtax.code"
    _description = 'Taxes Code'

    code = fields.Char(string="Código", size=12, )
    name = fields.Char(string="Nombre", size=160, )
    version = fields.Char(string="version", size=12)
    active = fields.Boolean(string="Active", default=True)


class xTaxRate(models.Model):
    _name = "xtax.rate"
    _description = 'Taxes Rates'

    code = fields.Char(string="Código", size=2, )
    name = fields.Char(string="Nombre", size=160, )
    amount = fields.Float(string="Tarifa", digits=(12,6), )
    active = fields.Boolean(string="Active", default=True)


class faeAccountTax(models.Model):
    _inherit = "account.tax"

    x_tax_code_id = fields.Many2one("xtax.code", string="Código Imp. DGT", ) 
    x_tax_rate_id = fields.Many2one("xtax.rate", string="Código tarifa", required=False, 
                                    help="Código de impuesto según la Dirección General De Tributación", )
    x_has_exoneration = fields.Boolean(string="Exonerado", required=False)
    x_exoneration_rate = fields.Float(string="Porc.exonerado", digits=(5,2), required=False, )
