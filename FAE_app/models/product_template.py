# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from lxml import etree
import logging

from odoo.exceptions import Warning, UserError, ValidationError

_logger = logging.getLogger(__name__)


class faeProduct(models.Model):
    _inherit = 'product.template'

    x_commercial_unit_measure = fields.Char(string='Commercial Unit', size=20)
    x_code_type = fields.Selection(string='Code Type DGT',
                                selection=[('01', 'Producto del vendedor'),
                                            ('02', 'Producto del comprador'),
                                            ('03', 'Producto asignado por la industria'),
                                            ('04', 'Código uso interno'),
                                            ('99', 'Otros ')],
                                default='04',
                                help='Tipo de código de producto según la DGT')
    x_cabys_code = fields.Char(string='Cat.ByS Code', size=13, help='Código de Bien o Servicio según la DGT')   # será descartado en próximas versiones
    x_cabys_code_id = fields.Many2one('xcabys.company', string='Cat.ByS Code', check_company=True,
                                help='Código de Bien o Servicio según la DGT')
    x_non_tax_deductible = fields.Boolean(string='Non Tax Deductible', default=False, help='Indica si el producto es no deducible de impuesto')
    x_other_charge_type_id  =  fields.Many2one('xother.charge.type', string='Tipo Otros Cargos DGT', required=False,
                                           help='Código de Hacienda para identificar otros tipos cargos')
    x_tariff_heading = fields.Char(string='Partida Arancelaria', copy=True, 
                                    help='La partida arancelaria para exportaciones')

    @api.onchange('company_id', 'x_cabys_code_id')
    def _onchange_x_cabys_code_id(self):
        if self.x_cabys_code_id and self.company_id and self.company_id != self.x_cabys_code_id.company_id:
            raise UserError('La compañia del CAByS no corresponde con la compañía ingresada')

    # dentro de poco tiempo este código será eliminado
    @api.onchange('x_cabys_code')
    def _onchange_x_cabys_code(self):
        if self.x_cabys_code and len(self.x_cabys_code) != 13:
            raise UserError('El código CAByS debe tener una longitud de 13 dígitos')

    @api.onchange('x_tariff_heading')
    def _onchange_x_tariff_heading(self):
        if self.x_tariff_heading and len(self.x_tariff_heading) != 12:
            raise UserError('El código de partida arancelaria debe tener una longitud de 12 dígitos')


# esto será desactivado en futuras versiones
class faeProductCategory(models.Model):
    _inherit = 'product.category'

    # este campo deja de utilizarse desde ago-2021, luego se eliminará
    x_cabys_code = fields.Char(string='Cat.ByS Code', size=13, help='Código de Bien o Servicio según la DGT')  