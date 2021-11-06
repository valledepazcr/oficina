# -*- coding: utf-8 -*-
import re
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import phonenumbers
import logging
from . import fae_utiles

_logger = logging.getLogger(__name__)


class PartnerElectronic(models.Model):
    _inherit = "res.partner"

    x_identification_type_id = fields.Many2one("xidentification.type", string="Tipo Identificación", required=False)
    x_commercial_name = fields.Char(string="Nombre Comercial", size=80, )
    x_country_county_id = fields.Many2one("xcountry.county", string="Cantón", required=False, )
    x_country_district_id = fields.Many2one("xcountry.district", string="Distrito", required=False, )

    x_economic_activity_id = fields.Many2one("xeconomic.activity", string="Actividad Económica", required=False, context={'active_test': False})

    x_email_fae = fields.Char(string="Email FAE", 
                              help='Correo exclusivo para enviar los documentos Electrónicos. Si está en blanco se envian al email registrado' )
    x_payment_method_id = fields.Many2one("xpayment.method", string="Método de Pago", required=False, )

    x_foreign_partner = fields.Boolean(string="Contacto del Exterior", required=False,
                                        help='Indica si el contacto es del exterior, por lo que las facturas son de tipo Exportación')

    x_special_tax_type = fields.Selection(string="Tipo Posición Fiscal",
                                            selection=[('E', 'Exonerado'),
                                                        ('R', 'Reducido')], 
                                        help='Indica si al cliente requiere un cálculo de impuesto especial (posición fiscal)' )

    x_exo_has_exoneration = fields.Boolean(string="Exonerado", required=False)
    x_exo_type_exoneration = fields.Many2one("xexo.authorization", string="Tipo Exoneración", required=False, )
    x_exo_exoneration_number = fields.Char(string="número exoneración", size=40, required=False, )
    x_exo_institution_name = fields.Char(string="Nombre Institución", size=160, required=False, 
                                        help='Nombre de la Institución que emitió la exoneración' )

    x_exo_date_issue = fields.Datetime(string="Fecha Hora Emisión", required=False, )
    x_exo_date_expiration = fields.Datetime(string="Fecha Expiración", required=False, )


    @api.onchange('x_identification_type_id', 'vat')
    def _onchange_identification_vat(self):
        if self.x_identification_type_id and self.vat:
            self.vat = self.vat.replace('-','').replace(' ','')
            error_msg = fae_utiles.val_identification_vat(self.x_identification_type_id.code, self.vat)
            if error_msg:
                raise UserError(error_msg)             
            partner_id = self.env['res.partner'].search([('x_identification_type_id','=',self.x_identification_type_id.id), ('vat','=',self.vat), ('id','!=',self._origin.id)], limit=1)
            if partner_id:
                raise UserError('Ya existe un cliente (%s) con la identificación : %s' % (partner_id.name, self.vat))

    @api.onchange('phone')
    def _onchange_phone(self):
        if self.phone:
            parsed = phonenumbers.parse(self.phone, self.country_id and self.country_id.code or 'CR')
            if not phonenumbers.is_possible_number(parsed):
                alert = {'title': 'Atención', 'message': 'Número de teléfono  parece incorrecto' }
                return {'value': {'phone': ''}, 'warning': alert}

    @api.onchange('mobile')
    def _onchange_mobile(self):
        if self.mobile:
            parsed = phonenumbers.parse(self.mobile, self.country_id and self.country_id.code or 'CR')
            if not phonenumbers.is_possible_number(parsed):
                alert = {'title': 'Atención', 'message': 'Número de teléfono parece incorrecto' }
                return {'value': {'mobile': ''}, 'warning': alert}

    @api.onchange('email')
    def _onchange_email(self):
        if self.email:
            if not re.match(r'^(\s?[^\s,]+@[^\s,]+\.[^\s,]+\s?,)*(\s?[^\s,]+@[^\s,]+\.[^\s,]+)$', self.email.lower()):
                vals = {'email': False}
                alerta = { 'title': 'Atención',
                           'message': 'El correo electrónico no cumple con una estructura válida. ' + str(self.email)
                          }
                return {'value': vals, 'warning': alerta}

    @api.onchange('x_email_fae')
    def _onchange_x_email_fae(self):
        if self.x_email_fae:
            if not re.match(r'^(\s?[^\s,]+@[^\s,]+\.[^\s,]+\s?,)*(\s?[^\s,]+@[^\s,]+\.[^\s,]+)$', self.x_email_fae.lower()):
                vals = {'x_email_fae': False}
                alerta = { 'title': 'Atención',
                           'message': 'El correo electrónico para FAE no cumple con una estructura válida. ' + str(self.x_email_fae)
                          }
                return {'value': vals, 'warning': alerta}

    def action_get_economic_activities(self):
        if self.vat:
            json_response = fae_utiles.get_economic_activities(self)

            if json_response["status"] == 200:
                activities_codes = list()
                activities = json_response["activities"]
                for activity in activities:
                    if activity["estado"] == "A":
                        activities_codes.append(activity["codigo"])

                economic_activities = self.env['xeconomic.activity'].with_context(active_test=False).search([('code', 'in', activities_codes)], limit=1)
                if economic_activities:
                    self.x_economic_activity_id = economic_activities.id

            else:
                alert = { 'title': json_response["status"], 'message': json_response["text"] }
                return {'value': {'vat': ''}, 'warning': alert}