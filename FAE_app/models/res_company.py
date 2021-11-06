# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from odoo.exceptions import UserError
import requests
import phonenumbers
import re
import datetime
from . import fae_enums
from . import fae_utiles
import logging

_logger = logging.getLogger(__name__)


class ResCompanyInherit(models.Model):
    _inherit = 'res.company'

    x_fae_mode = fields.Selection(string="Modo Conexión",
                                selection=[('N', 'Deshabilitado'),
                                           ('api-prod', 'Producción'),
                                           ('api-stag', 'Pruebas')],
                                required=True,
                                default='N')
    x_email_fae = fields.Char(string="Email Doc.Electrónicos",
                              help='Correo exclusivo para imprimir en documentos Electrónicos y enviar en el XML')

    x_identification_type_id = fields.Many2one("xidentification.type", string="Tipo Identificación", required=False)
    x_commercial_name = fields.Char(string="Nombre Comercial", size=80)
    x_country_county_id = fields.Many2one("xcountry.county", string="Cantón", required=False, )
    x_country_district_id = fields.Many2one("xcountry.district", string="Distrito", required=False, )
    
    x_economic_activity_id = fields.Many2one("xeconomic.activity", string="Actividad Económica", required=False,
                                             context={'active_test': False} )

    x_info_bank_accounts = fields.Html(string="Datos Cuenta", copy=False,
                                    help='HTML con los datos de la o las cuenta a través de las cuales los clientes pueden pagar la factura.'\
                                        'Este texto (HTML) será impreso en la factura', )
    x_line_info_invoice = fields.Html(string="Info Factura", copy=False,
                                    help='Información en formato HTML que será impreso en la factura.', )

    x_test_username = fields.Char(string='Usuario')
    x_test_password = fields.Char(string='Clave')
    x_test_pin = fields.Char(string='PIN')
    x_test_crypto_key = fields.Binary(string='LLave Criptográfica', attachment=False, copy=False)
    x_test_expire_date = fields.Date(string='Fecha Expiración')
    x_prod_username = fields.Char(string='Usuario', copy=False)
    x_prod_password = fields.Char(string='Clave', copy=False)
    x_prod_pin = fields.Char(string='PIN', copy=False)
    x_prod_crypto_key = fields.Binary(string='LLave Criptográfica', attachment=False, copy=False)
    x_prod_expire_date = fields.Date(string='Fecha Expiración', copy=False)

    # datos para generar el número de documentos
    x_sucursal = fields.Integer(string="Sucursal", required=False, default="1",
                                help='Sucursal default para ventas y aceptación de documentos electrónicos.')

    x_terminal = fields.Integer(string="Terminal", required=False, default="1",
                                help='Sucursal default para ventas y aceptación de documentos electrónicos.')

    # consecutivos de documentos
    x_sequence_FE_id = fields.Many2one("ir.sequence", string="Facturas Electrónicas", required=False)
    x_sequence_TE_id = fields.Many2one("ir.sequence", string="Tiquetes Electrónicos", required=False)
    x_sequence_NC_id = fields.Many2one("ir.sequence", string="NC Electrónicas", required=False, copy=False)
    x_sequence_ND_id = fields.Many2one("ir.sequence", string="ND Electrónicas", required=False, copy=False)
    x_sequence_FEE_id = fields.Many2one("ir.sequence", string="Facturas de Exportación", required=False, copy=False)
    x_sequence_FEC_id = fields.Many2one("ir.sequence", string="Facturas de Compra", required=False, copy=False)

    # consecutivos de recepción
    x_sequence_MRA_id = fields.Many2one("ir.sequence", string="Aceptación Total", required=False, copy=False)
    x_sequence_MRP_id = fields.Many2one("ir.sequence", string="Aceptación Parcial", required=False, copy=False)
    x_sequence_MRR_id = fields.Many2one("ir.sequence", string="Rechazo", required=False, copy=False)    

    # 
    x_load_bill_xml_lines = fields.Boolean(string="Carga líneas XML proveedor", default=False)
    x_def_expenses_account = fields.Many2one("account.account", string="Cuenta Gastos XML",
                                            help='Cuenta de Gastos default para carga de líneas del XML recibido del proveedor', )
    x_situacion_comprobante = fields.Selection(string="Conexión DGT",
                                selection=[('1', 'Comunicación Normal'),
                                           ('3', 'Sin Comunicación')],
                                default='1', )

    @api.onchange('x_identification_type_id', 'vat')
    def _onchange_identification_vat(self):
        if self.x_identification_type_id and self.vat:
            self.vat = self.vat.replace('-','')        
            error_msg = fae_utiles.val_identification_vat(self.x_identification_type_id.code, self.vat)
            if error_msg:
                raise UserError(error_msg)

    @api.onchange('x_email_fae')
    def _onchange_x_email_fae(self):
        if self.x_email_fae:
            emails = None
            lista = re.split(';|,', self.x_email_fae.replace(' ',''))
            for e in lista:
                if not re.match(r'^\s*(([^<>()\[\]\.,;:\s@\\"]+(\.[^<>()\[\]\.,;:\s@\\"]+)*)|(\\".+\\"))@(([^<>()\[\]\.,;:\s@\\"]+\.)+[^<>()\[\]\.,;:\s@\\"]{0,})\s*$', e.lower()):
                    vals = {'x_email_fae': False}
                    alerta = {'title': 'Atención',
                                'message': 'El correo electrónico para documentos electrónicos no cumple con una estructura válida. ' + str(e)
                            }
                    return {'value': vals, 'warning': alerta}
                emails = e if not emails else emails + '; ' + e
            self.x_email_fae = emails

    @api.onchange('x_test_crypto_key', 'x_test_pin')
    def get_cryptography_expire_test(self):
        # _logger.info('--  get_cryptography_expire_test:  pin %s,  key %s', self.x_test_pin, self.x_test_crypto_key)
        if self.x_test_crypto_key and self.x_test_pin:
            str_expire_date = fae_utiles.get_cryptography_expiration(self, 'api-stag')
            if str_expire_date:
                str_expire_date = str_expire_date.split()[0]
                # _logger.info('--  test crypto expire date: %s', str_expire_date)
                self.x_test_expire_date = datetime.datetime.strptime(str_expire_date, '%Y-%m-%d')

    @api.onchange('x_prod_crypto_key', 'x_prod_pin')
    def get_cryptography_expire_prod(self):
        if self.x_prod_crypto_key and self.x_prod_pin:
            str_expire_date = fae_utiles.get_cryptography_expiration(self, 'api-prod')
            if str_expire_date:
                self.x_prod_expire_date = str_expire_date
        # self.x_prod_expire_date = datetime.datetime.strptime('2-6-2021', '%d-%m-%Y')

    def verify_test_connection(self):
        self.ensure_one()
        return self.verify_connection('api-stag', self.x_test_username, self.x_test_password)

    def verify_production_connection(self):
        self.ensure_one()
        return self.verify_connection('api-prod', self.x_prod_username, self.x_prod_password)

    @staticmethod
    def verify_connection(x_fae_mode, username, password):
        if x_fae_mode == 'N':
            return
        else:
            url_dgt = fae_enums.dgt_url_token[x_fae_mode]
        
        # _logger.info('>>verify_connection: cliente_id %s  user %s  and pw %s ', x_fae_mode, username, password)

        params_passed = {'grant_type': 'password', 'client_id': x_fae_mode,
                         'username': username,
                         'password': password,
                         'access_token': url_dgt,
                         'client_secret': '', 'scope': ''}

        # execute request
        data_received = requests.post(url=url_dgt, data=params_passed)

        if 200 <= data_received.status_code <= 299:
            drj = data_received.json()
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                            'title': _('API Call Successful'),
                            'message': 'API Get Token Successful Client ID: %s - Token Time Expire: %d' % (x_fae_mode, drj.get('expires_in')),
                            'sticky': True,
                            }
                    }
        else:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                            'title': _('API Call Unsuccessful'),
                            'message': 'API Get Token Failed  Client ID: %s - Status Code: %d' % (x_fae_mode, data_received.status_code),
                            'sticky': True,
                            }
                    }

    def action_get_economic_activities(self):
        if self.vat:
            json_response = fae_utiles.get_economic_activities(self)

            if json_response["status"] == 200:
                activities_codes = list()
                activities = json_response["activities"]
                for activity in activities:
                    if activity["estado"] == "A":
                        activities_codes.append(activity["codigo"])

                economic_activities = self.env['xeconomic.activity'].with_context(active_test=False).search([('code', 'in', activities_codes)])

                for activity in economic_activities:
                    activity.active = True

                self.name = json_response["name"]
            else:
                alert = { 'title': json_response["status"], 'message': json_response["text"] }
                return {'value': {'vat': ''}, 'warning': alert}
        else:
            alert = { 'title': 'Atención', 'message': _('Company VAT is invalid') }
            return {'value': {'vat': ''}, 'warning': alert}
