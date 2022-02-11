from odoo import _

import requests
import json
import io
import re
import base64
import pytz
import datetime
import time

import phonenumbers
# import xmlsig

from xml.sax.saxutils import escape
from ..xades.context2 import XAdESContext2, PolicyId2, create_xades_epes_signature
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from xml.dom import minidom
from odoo.tools import float_compare, float_round

from . import fae_enums

import logging
from odoo.exceptions import UserError, Warning

try:
    from lxml import etree
except ImportError:
    from xml.etree import ElementTree

try:
    from OpenSSL import crypto
except(ImportError, IOError) as err:
    logging.info(err)

_logger = logging.getLogger(__name__)


# Diccionarios para guardar los datos del TOKEN según al compañía
tokens = {'api-stag':{}, 'api-prod':{}}
tokens_time = {'api-stag':{}, 'api-prod':{}}
tokens_expire = {'api-stag':{}, 'api-prod':{}}
tokens_refresh = {'api-stag':{}, 'api-prod':{}}


# Implementación de StringBuilder como C#
class XmlStrBuilder:
    _file_str = None

    def __init__(self):
        self._file_str = io.StringIO()

    def Append(self, data, if_add=True):
        if if_add == True:
            if data:
                self._file_str.write(data)

    def Tag(self, tag, data, if_add=True):
        if if_add == True:
            if not data:
                self._file_str.write('<' + tag + '></' + tag + '>') 
            else:
                self._file_str.write('<' + tag + '>' + data + '</' + tag + '>') 

    def Tag_prop(self, tag, prop, prop_value, data, if_add=True):
        if if_add == True:
            if not data:
                self._file_str.write(('<' + tag + ' %s="%s"></' + tag + '>') % (prop, prop_value) ) 
            else:
                self._file_str.write(('<' + tag + ' %s="%s">' + data + '</' + tag + '>') % (prop, prop_value) ) 
    
    def get_value(self):
        return self._file_str.getvalue()

    def __str__(self):
        return self._file_str.getvalue()


def get_datetime_dgt(fecha_hora=None):
    # La hora de Costa Rica está a 6 horas antes del Meridiano 0 (es UTC -6)
    dt_cr = (fecha_hora if fecha_hora else datetime.datetime.today()).astimezone(pytz.timezone('America/Costa_Rica'))
    fh_str = dt_cr.strftime("%Y-%m-%dT%H:%M:%S-06:00")
    return fh_str


def get_datetime(fecha_hora=None):
    dt_cr = (fecha_hora if fecha_hora else datetime.datetime.today()).astimezone(pytz.timezone('America/Costa_Rica'))
    fh_str = dt_cr.strftime("%Y-%m-%dT%H:%M:%S")
    return fh_str


def issue_date2str_dgt(fh_txt):
    return fh_txt + '-06:00'


def str_to_dbdate(date_str):
    fecha = None
    if date_str:
        if len(date_str) == 10:
            date_str += "T00:00:00"
        if len(date_str) > 19:
            date_str = date_str[:19]
        fecha = datetime.datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%S") + datetime.timedelta(hours=6)
    return fecha


def get_cryptography_expiration(company, x_fae_mode):
    if x_fae_mode == 'N':
        return ''
    try:
        # _logger.info('>> get_cryptography_expiration:  Inicio ')
        if x_fae_mode == 'api-prod':
            file = base64.b64decode(company.x_prod_crypto_key)
            pkcs12 = crypto.load_pkcs12(file, str.encode(company.x_prod_pin))
        else:
            file = base64.b64decode(company.x_test_crypto_key)
            pkcs12 = crypto.load_pkcs12(file, str.encode(company.x_test_pin))
        pem_data = crypto.dump_certificate(crypto.FILETYPE_PEM, pkcs12.get_certificate())
        cert = x509.load_pem_x509_certificate(pem_data, default_backend())

        expire_date = cert.not_valid_after      # date format is yyyy-m-d
    except Exception as error:
        expire_date = ''
    return str(expire_date)


def sign_xml(crypo_key, pin, xml):
    # _logger.info('>> sign_xml:  Entra, xml type: %s,  pin:  %s', type(xml), pin) 
    signature = create_xades_epes_signature()

    policy = PolicyId2()
    policy.id = fae_enums.policy_id
    ctx = XAdESContext2(policy)

    root = etree.fromstring(xml)
    root.append(signature)

    pkcs12 = crypto.load_pkcs12(base64.b64decode(crypo_key), str.encode(pin))
    ctx.load_pkcs12(pkcs12)
    ctx.sign(signature)

    # _logger.info('>> sign_xml:  Saliendo ')

    return etree.tostring(root, encoding='UTF-8', method='xml', xml_declaration=True, with_tail=False)


def val_identification_vat(identification_type_code, vat):
    error_msg = ''
    if identification_type_code and vat:
        if identification_type_code == 'E':
            if len(vat) == 0 or len(vat) > 20:
                error_msg = 'El número de identificación de Extranjero debe tener menos de 20 carateres'
        else:
            # Identificación 01,02,03,04
            vat = re.sub(r"[^0-9]+", "", vat)  # Elimina todo lo que no sea numeros
            if identification_type_code == '01':  # Cédula de Identidad
                if vat.isdigit() and len(vat) != 9:
                    error_msg = 'El número de cédula debe debe tener 9 dígitos y sin guiones'
            elif identification_type_code == '02':  # Céd. Jurídica
                if vat.isdigit() and len(vat) != 10:
                    error_msg = 'El número de céd.Jurídica debe tener 10 dígitos y sin guionefs'
            elif identification_type_code == '03':  # DIMEX
                if vat.isdigit() and len(vat) < 11 or len(vat) > 12:
                    error_msg = 'El DIMEX debe tener 11 o 12 dígitos y sin guiones'
            elif identification_type_code == '04':  # NITE
                if vat.isdigit() and len(vat) != 9:
                    error_msg = 'El NITE  debe tener 10 dígitos y sin guiones'
    return error_msg


def get_economic_activities(company):
    url_endpoint =  fae_enums.dgt_url['api-ae'] + company.vat
    try:
        params_passed = { 'Cache-Control': 'no-cache',
                          'Content-Type': 'application/x-www-form-urlencoded', }
        response = requests.get(url_endpoint, headers=params_passed, verify=False)
    except requests.exceptions.RequestException as ex:
        # _logger.error('>> get_economic_activities: Exception %s' % ex)
        return {'status': -1, 'text': 'Excepcion %s' % ex}

    if 200 <= response.status_code <= 299:
        response_json = { 'status': 200,
                          'activities': response.json().get('actividades'),
                          'name': response.json().get('nombre')
                        }
    else:
        # _logger.error('>> get_economic_activities: status_code: %s', response.status_code)
        response_json = {'status': response.status_code, 
                        'text': 'get_economic_activities failed: %s' % response.reason}
    return response_json


def get_exoneration_info(env, exoneration_number):
    response_json = None
    if exoneration_number:
        url_endpoint = fae_enums.dgt_url['api-ex'] + exoneration_number
        try:
            params_passed = { 'Cache-Control': 'no-cache',
                              'Content-Type': 'application/x-www-form-urlencoded', }
            response = requests.get(url_endpoint, headers=params_passed, verify=False)
        except requests.exceptions.RequestException as ex:
            return {'status': -1, 'text': 'Excepcion %s' % ex}

        if 200 <= response.status_code <= 299:
            tipo_documento = response.json().get('tipoDocumento')
            cod_tipo_documento = None
            exo_authorization_id = None
            if tipo_documento:
                cod_tipo_documento = tipo_documento.get('codigo')
                exo_authorization = env['xexo.authorization'].search([('code', '=', cod_tipo_documento)], limit=1)
                exo_authorization_id = exo_authorization.id if exo_authorization else None

            porcentaje_exoneracion = float(response.json().get('porcentajeExoneracion') or 0)
            tax_id = None
            if porcentaje_exoneracion > 0:
                tax = env['account.tax'].search([('type_tax_use', '=', 'sale'), ('active', '=', True),
                                                 ('x_has_exoneration', '=', True),
                                                 ('x_exoneration_rate', '=', float_round(porcentaje_exoneracion, precision_digits=2))], limit=1)
                tax_id = tax.id if tax else None
            femision = str_to_dbdate(response.json().get('fechaEmision'))
            fvence = str_to_dbdate(response.json().get('fechaVencimiento'))
            cabys_list = str(response.json().get('cabys')).lstrip('[').rstrip(']').replace("'", "").replace(" ", "")   # quita los corchetes [ ] y la comilla simple y espacios
            cabys_array = cabys_list.split(',')
            cabys_array.sort()
            cabys_list = None
            for codigo in cabys_array:
                codigo = codigo.strip("'")
                cabys_list = codigo if not cabys_list else cabys_list + ', ' + codigo
            response_json = {'status': 200,
                             'identificacion': response.json().get('identificacion'),
                             'numeroDocumento': response.json().get('numeroDocumento'),
                             'codTipoDocumento': cod_tipo_documento,
                             'exoAuthorization_id': exo_authorization_id,
                             'porcentajeExoneracion': response.json().get('porcentajeExoneracion'),
                             'tax_id': tax_id,
                             'nombreInstitucion': response.json().get('nombreInstitucion'),
                             'fechaEmision': femision,
                             'fechaVencimiento': fvence,
                             'poseeCabys': response.json().get('poseeCabys'),
                             'cabys': cabys_list
                             }
        else:
            response_json = {'status': response.status_code, 'text': 'get_exoneration_info failed: %s' % response.reason}
    return response_json


def gen_consecutivo(tipo_documento, consecutivo, sucursal_id, terminal_id):
    consecutivo10 = re.sub('[^0-9]', '', consecutivo.zfill(10))
    if len(consecutivo10) != 10:
        raise UserError('gen_consecutivo: La numeración debe de tener 10 dígitos')

    tipo_doc = fae_enums.tipo_doc_num[tipo_documento]

    consecutivo20 = (re.sub('[^0-9]', '', str(sucursal_id)).zfill(3) 
                      + re.sub('[^0-9]', '', str(terminal_id)).zfill(5) + tipo_doc + consecutivo10 )

    return consecutivo20

def gen_clave_hacienda(doc, tipo_documento, consecutivo, sucursal_id, terminal_id, situacion=None):

    if not doc.company_id.x_identification_type_id:
        raise UserError('gen_clave_hacienda: Seleccione el tipo de identificación del emisor en el perfil de la compañía')

    situacion_comprobante = situacion if situacion else doc.company_id.x_situacion_comprobante
    if not situacion_comprobante or situacion_comprobante not in ('1','2','3'):
        situacion_comprobante = '1'

    consecutivo20 = gen_consecutivo(tipo_documento, consecutivo, sucursal_id, terminal_id)

    cedula_emisor = re.sub('[^0-9]', '', doc.company_id.vat)
    cedula_emisor = str(cedula_emisor).zfill(12)

    # fec_doc = str(doc.invoice_date.day).zfill(2) + str(doc.invoice_date.month).zfill(2) + str(doc.invoice_date.year)[2:]
    # x_issue_date format yyyy-mm-ddThh24:mi:ss
    if doc._name == 'pos.order':
        sf_doc = doc.date_order.strftime('%Y%m%d')
    else:
        sf_doc = doc.date.strftime('%Y%m%d')
    fec_doc = doc.x_issue_date[8:10] + doc.x_issue_date[5:7] + doc.x_issue_date[2:4]

    codigo_pais = '506'
    clave_hacienda = codigo_pais + fec_doc + cedula_emisor[:12] + consecutivo20 + situacion_comprobante 

    # calcula el número de seguridad
    clave_hash = clave_hacienda[16:] + clave_hacienda[0:16]
    if sf_doc < '20220211':
        num_seguridad = (abs(hash(clave_hash)) % 99999998) + 1
    else:
        num_seguridad = 0
        for i in range(len(clave_hash)):
            if 48 <= ord(clave_hash[i]) <= 57:      # 0..9
                num_seguridad += (i+1)**int(clave_hash[i])
        num_seguridad = (num_seguridad % 99999998) + 1

    clave_hacienda = clave_hacienda + str(num_seguridad).zfill(8) 

    return {'consecutivo': consecutivo20, 'clave_hacienda': clave_hacienda }


# Convert String to encode64
def stringToBase64(s):
    return base64.b64encode(s).decode()


def get_inv_fname(inv):
    fname = ''
    if inv._name == 'pos.order': 
        move_type = 'out_refund' if inv.amount_total < 0 else 'out_invoice'
    else:
        move_type = inv.move_type
    
    if move_type in ('out_invoice', 'out_refund'):
        fname = inv.company_id.vat + '_' + inv.x_issue_date[:10].replace('-','') + '_' + inv.x_sequence
    elif inv.x_document_type == 'FEC':
        fname = inv.company_id.vat + '_FEC_' + inv.x_issue_date[:10].replace('-','') + '_' + inv.x_sequence     
    return fname


def get_token_hacienda(company_id, fae_mode):
    global tokens
    global tokens_time
    global tokens_expire
    global tokens_refresh

    token = tokens[fae_mode].get(company_id.id, False)
    token_time = tokens_time[fae_mode].get(company_id.id, False)
    token_expire = tokens_expire[fae_mode].get(company_id.id, 0)
    current_time = time.time()


    if token and (current_time - token_time < token_expire - 10):
        # _logger.info('>> get_token_hacienda: Existe un token cargado,  time_expire: %s ' % (str(token_expire)))
        token_hacienda = token
    else:
        # if token:
        #     # Procede a desconectar este token

        url_dgt_token = fae_enums.dgt_url_token[fae_mode]
        params_passed = {'client_id': fae_mode,
                         'grant_type': 'password', 'client_secret': '',
                         'username': company_id.x_prod_username if fae_mode == 'api-prod' else company_id.x_test_username,
                         'password': company_id.x_prod_password if fae_mode == 'api-prod' else company_id.x_test_password,
                         'access_token': url_dgt_token}
        try:
            
            # enviando solicitud post y guardando la respuesta como un objeto json
            response = requests.post(url=url_dgt_token, data=params_passed)
            drj = response.json()

            if 200 <= response.status_code <= 299:
                token_hacienda = drj.get('access_token')
                tokens[fae_mode][company_id.id] = token
                tokens_time[fae_mode][company_id.id] = time.time()
                tokens_expire[fae_mode][company_id.id] = drj.get('expires_in')
                tokens_refresh[fae_mode][company_id.id] = drj.get('refresh_expires_in')
                # _logger.info('>> get_token_hacienda: Token DGT obtenido. status: %s ' % (response.status_code))
            else:
                _logger.error('>> get_token_hacienda: Token DGT failed.  error: %s' % (response.status_code))

        except requests.exceptions.RequestException as e:
            raise Warning(_('Falla al obtener el TOKEN para comunicación con Hacienda. Exception: %s' % (e)))

    return token_hacienda


def consulta_clave(clave, token, fae_mode):
    if not token:
        raise Warning('request: No se recibió el TOKEN para connexión con Hacienda')
    if not clave:
        return {'status': 900 }
    
    url_dgt = fae_enums.dgt_url[fae_mode] + clave.rstrip()

    headers = {'Authorization': 'Bearer '+ token,
                'Cache-Control': 'no-cache',
                'Content-Type': 'application/x-www-form-urlencoded',
                }

    try:
        response = requests.request("GET", url_dgt, headers=headers)
        # _logger.error('>> consulta_clave:  response.json: %s', str(response.json()))

    except requests.exceptions.RequestException as error:
        _logger.error('>> consulta_clave: requests.exceptions %s' % error)
        return {'status': -1, 'text': 'Error: %s' % error}

    if 200 <= response.status_code <= 299:
        response_json = {'status': 200,
                        'ind-estado': response.json().get('ind-estado'),
                        'respuesta-xml': response.json().get('respuesta-xml')
                        }
    elif 400 <= response.status_code <= 499:
        # _logger.error('>> consulta_clave:  request failed.  status code: %s reason: %s', response.status_code, response.reason)
        response_json = {'status': 400, 'ind-estado': 'error'}
    else:
        # _logger.error('>> consulta_clave:  request failed.  status code: %s', response.status_code)
        response_json = {'status': response.status_code, 'text': 'token_hacienda failed: %s' % response.reason}
    
    return response_json


def consulta_doc_enviado(inv, token, fae_mode):
    if inv._name == 'pos.order': 
        move_type = 'out_refund' if inv.amount_total < 0 else 'out_invoice'
    else:
        move_type = inv.move_type        

    if not (move_type in ('out_invoice', 'out_refund') or inv.x_document_type == 'FEC'):
        return

    # consulta el estado de la clave en hacienda
    response_json = consulta_clave(inv.x_electronic_code50, token, fae_mode)
    status = response_json['status']

    ind_estado =''
    if status == 200:
        ind_estado = response_json.get('ind-estado')
    elif status == 400:
        ind_estado = response_json.get('ind-estado')
    else:
        status = -1
    
    if status != 200:
        _logger.error('>> consulta_doc_enviado: Abortando por status code != 200, clave50: %s, status: %s, jresponse: %s '
                      , inv.x_electronic_code50, str(status), str(response_json) )

    if ind_estado:
        ind_estado = ind_estado.lower()

    fname_resp = get_inv_fname(inv) + '_resp.xml'

    if not inv.x_error_count:
        inv.x_error_count = 0

    if ind_estado == 'aceptado':
        inv.x_state_dgt = '1'
        inv.x_xml_respuesta = response_json.get('respuesta-xml')
        inv.x_xml_respuesta_fname = fname_resp
        inv.x_response_date = datetime.datetime.today()
        inv.x_mensaje_respuesta = get_mensaje_respuesta(inv.x_xml_respuesta)

    elif ind_estado in ('firma_invalida', 'rechazado'):
        inv.x_xml_respuesta_fname = fname_resp
        inv.x_xml_respuesta = response_json.get('respuesta-xml')
        inv.x_response_date = datetime.datetime.today()
        inv.x_mensaje_respuesta = get_mensaje_respuesta(inv.x_xml_respuesta)
        if ind_estado == 'firma_invalida' and inv.x_error_count <= 10:
            inv.x_state_dgt = 'FI'
            inv.x_error_count += 1
        else:
            inv.x_state_dgt = '2'
            inv.x_state_email = 'NOE'

    elif ind_estado == 'error' or inv.x_error_count > 10:
        inv.x_state_dgt = 'ERR'
        inv.x_state_email = 'NOE'
        inv.x_mensaje_respuesta = str(response_json)

    elif ind_estado != 'error' and ind_estado.find('procesando') < 0:
        inv.x_error_count += 1
        inv.x_state_dgt = 'PRO'
        inv.x_mensaje_respuesta = str(response_json)
    
    # _logger.info('>> fae_utiles.consulta_doc_enviado: numero: %s,  ind_estado: %s', inv.x_sequence, ind_estado )
    return inv.x_state_dgt


def get_mensaje_respuesta(xml_respuesta):    
    mensaje = ""
    if xml_respuesta:
        try:
            doc = minidom.parseString( base64.decodebytes(xml_respuesta) )
            mensaje = doc.getElementsByTagName('DetalleMensaje')[0].childNodes[0].data;
        except Exception as error:
            _logger.info('>> fae_utiles.get_mensaje_respuesta: error: %s', error )
            pass
    return mensaje[:800]

# Genera xml para el documento electrónico
def gen_xml_v43(inv, sale_condition_code, total_servicio_gravado, total_servicio_exento, total_servicio_exonerado,
    total_mercaderia_gravado, total_mercaderia_exento, total_mercaderia_exonerado, total_otros_cargos,
    total_iva_devuelto, base_subtotal, total_impuestos, total_descuento,
    lines, otrosCargos, currency_rate, other_text, tipo_documento_referencia, numero_documento_referencia,
    fecha_emision_referencia, codigo_referencia, razon_referencia ):

    numero_linea = 0
    payment_methods_code = []
    if inv._name == 'pos.order':
        # Documento de POS
        economic_activity_code = inv.company_id.x_economic_activity_id.code
        plazo_credito = '0'
        ref_oc = None
        for payment in inv.payment_ids:
            payment_code = None
            if payment.payment_method_id.x_payment_method_id:
                 payment_code = payment.payment_method_id.x_payment_method_id.code
            else:
                payment_code = '01' 
            if payment_code not in payment_methods_code:
                payment_methods_code.append(payment_code)
                if len(payment_methods_code) >= 4:
                    break
    else:
        # Documento Facturación (Invoice )
        economic_activity_code = inv.x_economic_activity_id.code
        plazo_credito = str(inv.invoice_payment_term_id and inv.invoice_payment_term_id.line_ids[0].days or 0)
        if inv.x_payment_method_id:
            payment_methods_code.append(str(inv.x_payment_method_id.code))
        ref_oc = inv.ref
    
    if not payment_methods_code:
        payment_methods_code.append('01')       # efectivo por default si no hay metodos de pago

    cod_moneda = str(inv.currency_id.name)

    if inv.x_document_type == 'FEC':
        issuing_company = inv.partner_id
        receiver_company = inv.company_id
        email_emisor = inv.partner_id.email
    else:
        issuing_company = inv.company_id
        receiver_company = inv.partner_id
        email_emisor = inv.company_id.x_email_fae or inv.company_id.email

    # _logger.info('>> gen_xml_v43: Inicia el XML, # %s ', inv.x_sequence)

    # inicializa la variable para el XML del documento
    xmlstr = XmlStrBuilder()
    xmlotros = XmlStrBuilder()

    xmlstr.Append('<' + fae_enums.tipo_doc_name[inv.x_document_type] + ' xmlns="' + fae_enums.xmlns_hacienda[inv.x_document_type] + '" ')
    xmlstr.Append('xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema" ')
    xmlstr.Append('xsi:schemaLocation="' + fae_enums.schema_location[inv.x_document_type] + '" ')
    xmlstr.Append('xmlns:ds="http://www.w3.org/2000/09/xmldsig#" >')

    xmlstr.Tag('Clave', inv.x_electronic_code50)
    xmlstr.Tag('CodigoActividad', economic_activity_code)
    xmlstr.Tag('NumeroConsecutivo', inv.x_sequence )
    xmlstr.Tag('FechaEmision', issue_date2str_dgt(inv.x_issue_date)  )

    xmlstr.Append('<Emisor>')
    xmlstr.Tag('Nombre', escape(issuing_company.name)[:100] )
    xmlstr.Append('<Identificacion>')
    xmlstr.Tag('Tipo', issuing_company.x_identification_type_id.code )
    xmlstr.Tag('Numero', issuing_company.vat )
    xmlstr.Append('</Identificacion>')

    xmlstr.Tag('NombreComercial', escape(issuing_company.x_commercial_name or ''), (issuing_company.x_commercial_name and True or False) )
    
    xmlstr.Append('<Ubicacion>')
    xmlstr.Tag('Provincia', issuing_company.state_id.code )
    xmlstr.Tag('Canton', issuing_company.x_country_county_id.code )
    xmlstr.Tag('Distrito', issuing_company.x_country_district_id.code )
    xmlstr.Tag('OtrasSenas', escape(issuing_company.street or 'No indicada') )
    xmlstr.Append('</Ubicacion>')

    if issuing_company.phone:
        phone = phonenumbers.parse(issuing_company.phone, (issuing_company.country_id.code or 'CR'))
        xmlstr.Append('<Telefono>')
        xmlstr.Tag('CodigoPais', str(phone.country_code) )
        xmlstr.Tag('NumTelefono', str(phone.national_number) )
        xmlstr.Append('</Telefono>')

    xmlstr.Tag('CorreoElectronico', str(email_emisor) )
    xmlstr.Append('</Emisor>')

    # _logger.info('>> gen_xml_v43: Inicia tag Receptor')

    if inv.x_document_type == 'TE' or (inv.x_document_type == 'NC' and not receiver_company.vat):
        pass
    else:
        id_code = None
        vat = None if not receiver_company.vat else re.sub('[^0-9]', '', receiver_company.vat)
        if not receiver_company.x_identification_type_id and vat:
            # Si no han puesto  el tipo de identificación en el receptor, entonces se trata de calcular
            if len(vat) == 9:  # cedula fisica
                id_code = '01'
            elif len(vat) == 10:  # cedula juridica
                id_code = '02'
            elif len(vat) == 11 or len(vat) == 12:  # dimex
                id_code = '03'
            else:
                id_code = '04'
        elif receiver_company.x_identification_type_id:
            id_code = receiver_company.x_identification_type_id.code

        if receiver_company.name:
            xmlstr.Append('<Receptor>')
            xmlstr.Tag('Nombre', escape(str(receiver_company.name))[:99] )

            if inv.x_document_type == 'FEE' or id_code == 'E':
                if receiver_company.vat:
                    xmlstr.Tag('IdentificacionExtranjero',  receiver_company.vat[:20] )
            else:
                xmlstr.Append('<Identificacion>')
                xmlstr.Tag('Tipo', id_code )
                xmlstr.Tag('Numero', vat )
                xmlstr.Append('</Identificacion>')

            if inv.x_document_type != 'FEE':
                if receiver_company.state_id and receiver_company.x_country_county_id and receiver_company.x_country_district_id:
                    xmlstr.Append('<Ubicacion>')
                    xmlstr.Tag('Provincia', str(receiver_company.state_id.code or '') )
                    xmlstr.Tag('Canton', str(receiver_company.x_country_county_id.code or '') )
                    xmlstr.Tag('Distrito', str(receiver_company.x_country_district_id.code or '') )                    
                    xmlstr.Tag('OtrasSenas', escape(receiver_company.street or 'No indicada') )
                    xmlstr.Append('</Ubicacion>')

                if receiver_company.phone:
                    try:
                        phone = phonenumbers.parse(receiver_company.phone, (receiver_company.country_id.code or 'CR'))
                        xmlstr.Append('<Telefono>')
                        xmlstr.Tag('CodigoPais', str(phone.country_code) )
                        xmlstr.Tag('NumTelefono', str(phone.national_number) )
                        xmlstr.Append('</Telefono>')
                    except:
                        pass

            # valida que el correo receptor
            match = receiver_company.email and re.match( r'^(\s?[^\s,]+@[^\s,]+\.[^\s,]+\s?,)*(\s?[^\s,]+@[^\s,]+\.[^\s,]+)$', receiver_company.email.lower())
            if match:
                email_receptor = receiver_company.email
            else:
                email_receptor = None

            xmlstr.Tag('CorreoElectronico', email_receptor, (email_receptor and True or False) )
            xmlstr.Append('</Receptor>')

    xmlstr.Tag('CondicionVenta', sale_condition_code )
    xmlstr.Tag('PlazoCredito', plazo_credito )
    payment_method_length = len(payment_methods_code)
    for payment_method_counter in range(payment_method_length):
        xmlstr.Tag('MedioPago', payment_methods_code[payment_method_counter] )

    # _logger.info('>> gen_xml_v43: Inicia tag DetalleServicio')
    # lineas del documento
    xmlstr.Append('<DetalleServicio>')

    jlines = json.loads(lines)

    for (k, v) in jlines.items():
        numero_linea = numero_linea + 1

        xmlstr.Append('<LineaDetalle>')
        xmlstr.Tag('NumeroLinea', str(numero_linea))

        if inv.x_document_type == 'FEE' and v.get('partidaArancelaria'):
            xmlstr.Tag('PartidaArancelaria', str(v['partidaArancelaria']) )

        if v.get('codigoCabys'):
            xmlstr.Tag('Codigo', (v['codigoCabys']) )

        if v.get('codigo'):
            xmlstr.Append('<CodigoComercial>')
            xmlstr.Tag('Tipo', '04')
            xmlstr.Tag('Codigo', (v['codigo']) )
            xmlstr.Append('</CodigoComercial>')

        xmlstr.Tag('Cantidad', str(v['cantidad']) )
        xmlstr.Tag('UnidadMedida', str(v['unidadMedida']) )
        xmlstr.Tag('Detalle', str(v['detalle']) )
        xmlstr.Tag('PrecioUnitario', str(v['precioUnitario']) )
        xmlstr.Tag('MontoTotal', str(v['montoTotal']) )

        if v.get('montoDescuento'):
            xmlstr.Append('<Descuento>')
            xmlstr.Tag('MontoDescuento', str(v['montoDescuento']) )
            if v.get('naturalezaDescuento'):
                xmlstr.Tag('NaturalezaDescuento', str(v['naturalezaDescuento']) )
            xmlstr.Append('</Descuento>')

        xmlstr.Tag('SubTotal', str(v['subtotal']) )

        if v.get('BaseImponible') and inv.x_document_type != 'FEE':
            xmlstr.Tag('BaseImponible', str(v['BaseImponible']) )

        if v.get('impuesto'):
            for (a, b) in v['impuesto'].items():
                tax_rate_code = str(b['cod_tarifa_imp'])
                if tax_rate_code.isdigit():
                    xmlstr.Append('<Impuesto>')
                    xmlstr.Tag('Codigo', str(b['codigo']) )
                    xmlstr.Tag('CodigoTarifa', tax_rate_code )
                    xmlstr.Tag('Tarifa', str(b['tarifa']) )
                    xmlstr.Tag('Monto', str(b['monto']) )

                    if inv.x_document_type != 'FEE':
                        if b.get('exoneracion'):
                            xmlstr.Append('<Exoneracion>')
                            xmlstr.Tag('TipoDocumento', receiver_company.x_exo_type_exoneration.code )
                            xmlstr.Tag('NumeroDocumento', receiver_company.x_exo_exoneration_number )
                            xmlstr.Tag('NombreInstitucion', receiver_company.x_exo_institution_name )
                            fechaEmision = None
                            if receiver_company.x_exo_date_issue:
                                fechaEmision = get_datetime(receiver_company.x_exo_date_issue)
                            xmlstr.Tag('FechaEmision', fechaEmision)
                            xmlstr.Tag('PorcentajeExoneracion', str(int(b['exoneracion']['porc_exonera'])) )
                            xmlstr.Tag('MontoExoneracion', str(b['exoneracion']['monto_exonera']) )
                            xmlstr.Append('</Exoneracion>')
                    xmlstr.Append('</Impuesto>')
            xmlstr.Tag('ImpuestoNeto', str(v['impuestoNeto']) )
 
        xmlstr.Tag('MontoTotalLinea', str(v['montoTotalLinea']) )
        xmlstr.Append('</LineaDetalle>')

    xmlstr.Append('</DetalleServicio>')
    
    # Otros Cargos
    if otrosCargos:
        xmlstr.Append('<OtrosCargos>')
        for num_oc in otrosCargos:
            otro_cargo = otrosCargos[num_oc]
            xmlstr.Tag('TipoDocumento', str(otro_cargo['TipoDocumento']) )

            if otro_cargo.get('NumeroIdentidadTercero'):
                xmlstr.Tag('NumeroIdentidadTercero', str(otro_cargo['IdentidadTercero']) )

            if otro_cargo.get('NombreTercero'):
                xmlstr.Tag('NombreTercero', str(otro_cargo['NombreTercero']) )

            xmlstr.Tag('Detalle', str(otro_cargo['Detalle']) )

            if otro_cargo.get('Porcentaje'):
                xmlstr.Tag('Porcentaje', str(otro_cargo['Porcentaje']) )

            xmlstr.Tag('MontoCargo', str(otro_cargo['MontoCargo']) )
        xmlstr.Append('</OtrosCargos>')

    # Resumen del documento
    xmlstr.Append('<ResumenFactura>')
    xmlstr.Append('<CodigoTipoMoneda>')
    xmlstr.Tag('CodigoMoneda', cod_moneda)
    xmlstr.Tag('TipoCambio', str(currency_rate))
    xmlstr.Append('</CodigoTipoMoneda>')

    xmlstr.Tag('TotalServGravados', str(total_servicio_gravado) )
    xmlstr.Tag('TotalServExentos', str(total_servicio_exento) )
    xmlstr.Tag('TotalServExonerado', str(total_servicio_exonerado), (inv.x_document_type != 'FEE') )
    xmlstr.Tag('TotalMercanciasGravadas', str(total_mercaderia_gravado) )
    xmlstr.Tag('TotalMercanciasExentas', str(total_mercaderia_exento) )
    xmlstr.Tag('TotalMercExonerada', str(total_mercaderia_exonerado), (inv.x_document_type != 'FEE') )

    total_gravado = round(total_servicio_gravado + total_mercaderia_gravado, 5)
    total_exento = round(total_servicio_exento + total_mercaderia_exento, 5)
    total_exonerado = round(total_servicio_exonerado + total_mercaderia_exonerado, 5)
    total_venta = round(total_gravado + total_exento + total_exonerado, 5)

    xmlstr.Tag('TotalGravado', str(total_gravado) )
    xmlstr.Tag('TotalExento', str(total_exento) )
    xmlstr.Tag('TotalExonerado', str(total_exonerado), (inv.x_document_type != 'FEE') )

    xmlstr.Tag('TotalVenta', str(total_venta) )

    xmlstr.Tag('TotalDescuentos', str(total_descuento) )
    xmlstr.Tag('TotalVentaNeta', str(base_subtotal) )
    xmlstr.Tag('TotalImpuesto', str(total_impuestos) )

    if total_iva_devuelto:
        xmlstr.Tag('TotalIVADevuelto', str(round(total_iva_devuelto, 5)) )

    xmlstr.Tag('TotalOtrosCargos', str(total_otros_cargos) )

    total_doc = round(base_subtotal + total_impuestos + total_otros_cargos - total_iva_devuelto, 5)
    xmlstr.Tag('TotalComprobante', str(total_doc) )
    xmlstr.Append('</ResumenFactura>')

    if tipo_documento_referencia and numero_documento_referencia and fecha_emision_referencia:
        xmlstr.Append('<InformacionReferencia>')
        xmlstr.Tag('TipoDoc', str(tipo_documento_referencia) )
        xmlstr.Tag('Numero', str(numero_documento_referencia) )
        xmlstr.Tag('FechaEmision', fecha_emision_referencia )
        xmlstr.Tag('Codigo', str(codigo_referencia) )
        xmlstr.Tag('Razon', str(razon_referencia) )
        xmlstr.Append('</InformacionReferencia>')

    #  Genera datos del tag Otros
    if inv.x_document_type in ('FE','TE') and receiver_company.vat in ('3101420995', '3101011086', '3101375519', '3101695692'):
        # Compañía Galletas Pozuela, Americana de Helados, Nacional de Chocolates y Nutresa
        ref_oc = ref_oc if ref_oc else ''
        xmlotros.Tag_prop('OtroTexto', 'codigo', 'NumeroPedido', str(escape(ref_oc)) )

    if other_text:
        xmlotros.Tag('OtroTexto', str(escape(other_text)) )

    if xmlotros.get_value():
        xmlstr.Append('<Otros>')
        xmlstr.Append( xmlotros.get_value() )
        xmlstr.Append('</Otros>')

    xmlstr.Append('</' + fae_enums.tipo_doc_name[inv.x_document_type] + '>')
    
    # _logger.info('>> gen_xml_v43: XML Generado')

    return str(xmlstr)

# Genera xml por aceptación o rechazo de documentos
def gen_xml_approval(doc):
    mensaje = None
    if doc.code_accept == 'A':
        mensaje = 1
    elif doc.code_accept == 'P':
        mensaje = 2
    elif doc.code_accept == 'R':
        mensaje = 3

    # inicializa la variable para el XML del documento
    xmlstr = XmlStrBuilder()

    url_loc = 'https://cdn.comprobanteselectronicos.go.cr/xml-schemas/v4.3/'
    xmlstr.Append('<MensajeReceptor ')
    xmlstr.Append('xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="' + url_loc + 'mensajeReceptor '
                  + url_loc + 'mensajeReceptor.xsd" xmlns="' + url_loc + 'mensajeReceptor" >')

    xmlstr.Tag('Clave', doc.issuer_electronic_code50)
    xmlstr.Tag('NumeroCedulaEmisor', doc.issuer_identification_num)
    xmlstr.Tag('FechaEmisionDoc', doc.bill_date.strftime("%Y-%m-%dT%H:%M:%S") )  
    xmlstr.Tag('Mensaje', str(mensaje))

    motivo_aceptacion = doc.motive_accept
    if doc.code_accept in ('P','R') and not motivo_aceptacion:
        motivo_aceptacion = 'Sin motivo indicado'
    xmlstr.Tag('DetalleMensaje', escape(motivo_aceptacion or ''), (motivo_aceptacion and True or False) )
    xmlstr.Tag('MontoTotalImpuesto', str(doc.amount_tax), (doc.include_tax_tag and doc.amount_tax != 0) )

    if doc.tax_use_code_id.code != '05':
        xmlstr.Tag('CodigoActividad', doc.company_id.x_economic_activity_id.code )
    
    if doc.tax_use_code_id:
        xmlstr.Tag('CondicionImpuesto', doc.tax_use_code_id.code)
        if doc.tax_use_code_id.code != '05' and doc.amount_tax_credit and doc.amount_tax_credit > 0:
            xmlstr.Tag('MontoTotalImpuestoAcreditar', str(doc.amount_tax_credit) )
        if doc.tax_use_code_id.code != '05' and doc.amount_tax_expenses and doc.amount_tax_expenses > 0:
            xmlstr.Tag('MontoTotalDeGastoAplicable', str(doc.amount_tax_credit) )

    xmlstr.Tag('TotalFactura', str(doc.amount_total))
    xmlstr.Tag('NumeroCedulaReceptor', str(doc.identification_number))
    xmlstr.Tag('NumeroConsecutivoReceptor', doc.sequence)
    xmlstr.Append('</MensajeReceptor>')

    return str(xmlstr)

# Parser XML recibidos (Document or Response)
def parser_xml(identification_type_obj, company_obj, currency_obj, origin, docxml=None):
    # Esta función se utiliza para parsear el contenido de un fichero xml

    xml_doc = docxml
    if origin == 'manual':
        docxml = base64.decodebytes(docxml)

    elif isinstance(docxml, str):
        xml_doc = base64.encodebytes(docxml.encode('utf-8'))

    doc = minidom.parseString(docxml)
    # xml_doc = base64.encodebytes(docxml)

    # _logger.info('>> fae_utiles.parser_xml: get elements')
    es_mensaje_hacienda = doc.getElementsByTagName('MensajeHacienda')
    clave_hacienda = doc.getElementsByTagName('Clave')[0].childNodes[0].data;
    document_type = None
    issuer_identification_type = None
    identification_type_id = None
    identification_number = None
    if clave_hacienda:
        document_type = clave_hacienda[29:31] # numero del tipo de documento
    values = {}

    if clave_hacienda and not es_mensaje_hacienda:
        # El archivo es un documento electrónico

        #  _logger.info('>> fae_utiles.parser_xml: clave_hacienda %s   NO es_mensaje_hacienda', clave_hacienda)
        document_type = fae_enums.num_tipo_doc[document_type]
        tag_issuer = doc.getElementsByTagName('Emisor')[0]

        tag_ResumenFactura = doc.getElementsByTagName('ResumenFactura')[0]
        tag_Receptor = doc.getElementsByTagName('Receptor')[0]
        if tag_Receptor:
            tag_identif_receptor = getElementTag(tag_Receptor, 'Identificacion')
            if tag_identif_receptor:
                identification_type = getElementTag_data(tag_identif_receptor.getElementsByTagName('Tipo'))
                identification_number = getElementTag_data(tag_identif_receptor.getElementsByTagName('Numero'))

                company_id = None
                company = company_obj.filtered(lambda c: c.vat == identification_number)
                for cia in company:
                    company_id = cia.id

                rec = identification_type_obj.filtered(lambda t: t.code == identification_type)
                identification_type_id = (rec and rec.id or None)
            elif document_type == 'NC':
                # La documento no trae información de la identificación del receptor
                tag_info_referencia = getElementTag(doc, 'InformacionReferencia')
                if tag_info_referencia:
                    clave_hacienda_ref = getElementTag_data(tag_info_referencia.getElementsByTagName('Numero'))
                    incoming_doc = company_obj.env['xfae.incoming.documents'].search([('issuer_electronic_code50', '=', clave_hacienda_ref)], limit=1)
                    if incoming_doc:
                        company_id = incoming_doc.company_id.id
                        identification_number = incoming_doc.identification_number
                        identification_type_id = incoming_doc.issuer_identification_type_id.id

        issuer_identification_type = tag_issuer.getElementsByTagName('Tipo')[0].childNodes[0].data

        tag_tipoMoneda = tag_ResumenFactura.getElementsByTagName('CodigoTipoMoneda')
        if not tag_tipoMoneda:
            currency = 'CRC'
        else:
            tag_tipoMoneda = tag_tipoMoneda[0]
            currency = getElementTag_data(tag_tipoMoneda.getElementsByTagName('CodigoMoneda') )
            if not currency:
                currency = 'CRC'
        rec = currency_obj.filtered(lambda a: a.name == currency)        
        currency_id = (rec and rec.id or None)

        # amount_tax = tag_ResumenFactura.getElementsByTagName('TotalImpuesto')[0].childNodes[0].data
        amount_tax = getElementTag_data( tag_ResumenFactura.getElementsByTagName('TotalImpuesto') )
        include_tax_tag = False
        if amount_tax:
            include_tax_tag = True

        values = {
            'company_id': company_id,
            'identification_type_id': identification_type_id,
            'identification_number': identification_number,            
            'issuer_electronic_code50': clave_hacienda,
            'issuer_sequence': doc.getElementsByTagName('NumeroConsecutivo')[0].childNodes[0].data,
            'document_type': document_type,
            'issuer_name': tag_issuer.getElementsByTagName('Nombre')[0].childNodes[0].data,
            'issuer_identification_type': issuer_identification_type,
            'issuer_identification_num': tag_issuer.getElementsByTagName('Numero')[0].childNodes[0].data,
            'bill_date': doc.getElementsByTagName('FechaEmision')[0].childNodes[0].data,
            'include_tax_tag': include_tax_tag,
            'currency_id': currency_id,
            'amount_tax': amount_tax,
            'amount_total': tag_ResumenFactura.getElementsByTagName('TotalComprobante')[0].childNodes[0].data,
            'issuer_xml_doc': xml_doc,
            'origin': origin,
        }
    elif clave_hacienda and es_mensaje_hacienda:
        # El archivo es un Mensaje de Hacienda
        # _logger.info('>> fae_utiles.parser_xml: clave_hacienda %s   es_mensaje_hacienda', clave_hacienda)
        identification_number = getElementTag_data(doc.getElementsByTagName('NumeroCedulaReceptor'))
        company_id = None
        company = company_obj.filtered(lambda c: c.vat == identification_number)
        for cia in company:
            company_id = cia.id

        issuer_identification_type = getElementTag_data(doc.getElementsByTagName('TipoIdentificacionEmisor'))

        values = {
            'company_id': company_id,
            'identification_number': identification_number,
            'issuer_identification_type': issuer_identification_type,
            'issuer_identification_num': doc.getElementsByTagName('NumeroCedulaEmisor')[0].childNodes[0].data,
            'issuer_electronic_code50': clave_hacienda,
            'issuer_sequence': clave_hacienda[21:41],
            'issuer_xml_response': xml_doc,
            'response_state':  doc.getElementsByTagName('Mensaje')[0].childNodes[0].data,
            'amount_total': doc.getElementsByTagName('TotalFactura')[0].childNodes[0].data,
            'origin': origin,
            }

    if issuer_identification_type:
        rec = identification_type_obj.filtered(lambda t: t.code == issuer_identification_type)        
        values.update({'issuer_identification_type_id': (rec and rec.id or None)})

    return values

# Envia a hacienda el XML del documento electronico
def send_xml_fe(inv, date_issue, xml, fae_mode):
    # _logger.info('>> send_xml_fe:  Entro al send_xml_fe')

    token = get_token_hacienda(inv.company_id, fae_mode)
    if not token:
        raise Warning('send_xml_fe: No se pudo obtener el token para connexión con Hacienda')

    # Determina el URL de envio 
    url_dgt = fae_enums.dgt_url[fae_mode]

    # _logger.info('>> send_xml_fe:  URL: %s', url_dgt)

    xml_base64 = stringToBase64(xml)

    data = {'clave': inv.x_electronic_code50,
            'fecha': issue_date2str_dgt(date_issue),
            'emisor': {
                'tipoIdentificacion': inv.company_id.x_identification_type_id.code,
                'numeroIdentificacion': inv.company_id.vat
            },
            'comprobanteXml': xml_base64
            }

    if (inv.partner_id and inv.partner_id.vat and inv.partner_id.x_identification_type_id and inv.partner_id.x_identification_type_id.code != 'E'):
        data['receptor'] = {'tipoIdentificacion': inv.partner_id.x_identification_type_id.code,
                            'numeroIdentificacion': inv.partner_id.vat
                            }

    json_hacienda = json.dumps(data)

    # if inv.x_state_dgt in ('ERR', 'ENV'):
    #     _logger.info('>> send_xml_fe:  Json a enviar: %s', json_hacienda)

    headers = {'Authorization': 'Bearer ' + token, 'Content-type': 'application/json'}

    try:
        # enviando solicitud post y guardando la respuesta como un objeto json
        response = requests.request("POST", url_dgt, data=json_hacienda, headers=headers)

        # if response.status_code != 202:
        if not(200 <= response.status_code <= 299):
            error_caused_by = response.headers.get('X-Error-Cause') if 'X-Error-Cause' in response.headers else ''
            error_caused_by += response.headers.get('validation-exception', '')
            # _logger.info('Status: {}, Text {}'.format(response.status_code, error_caused_by))

            return {'status': response.status_code, 'text': error_caused_by}
        else:
            return {'status': response.status_code, 'text': response.reason}

    except ImportError:
        raise Warning('Error tratando de enviar el XML a Hacienda')


# Envia a hacienda el XML de aceptacion o rechazo
def send_xml_acepta_rechazo(doc, xml, fae_mode):
    # _logger.info('>> send_xml_acepta_rechazo:  Entro al send_xml_fe')

    token = get_token_hacienda(doc.company_id, fae_mode)
    if not token:
        raise Warning('send_xml_acepta_rechazo: No se pudo obtener el token para connexión con Hacienda')

    # Determina el URL de envio 
    url_dgt = fae_enums.dgt_url[fae_mode]

    # _logger.info('>> send_xml_acepta_rechazo:  URL: %s', url_dgt)
    xml_base64 = stringToBase64(xml)

    dt_cr_dgt = get_datetime_dgt(doc.send_date)
    data = {
        'clave': doc.issuer_electronic_code50,
        "fecha": dt_cr_dgt,
        'emisor': { 'tipoIdentificacion': str(doc.issuer_identification_type),
                    'numeroIdentificacion': str(doc.issuer_identification_num),
                },
        'receptor': { 'tipoIdentificacion': str(doc.company_id.x_identification_type_id.code),
                    'numeroIdentificacion': doc.company_id.vat,
                },
        'consecutivoReceptor': doc.sequence,
        'comprobanteXml': xml_base64,
    }

    json_hacienda = json.dumps(data)

    headers = {'Authorization': 'Bearer ' + token, 'Content-type': 'application/json'}

    try:
        # enviando solicitud post y guardando la respuesta como un objeto json
        response = requests.request("POST", url_dgt, data=json_hacienda, headers=headers)

        if not(200 <= response.status_code <= 299):
            error_caused_by = response.headers.get('X-Error-Cause') if 'X-Error-Cause' in response.headers else ''
            error_caused_by += response.headers.get('validation-exception', '')
            # _logger.info('Status: {}, Text {}'.format(response.status_code, error_caused_by))

            return {'status': response.status_code, 'text': error_caused_by}
        else:
            return {'status': response.status_code, 'text': response.reason}

    except ImportError:
        raise Warning('Error tratando de enviar el Mensajes de Aceptación o Rechazo a Hacienda')


# Envia email a un partner los documentos del documento electrónico
def send_mail_fae(inv, full_mail_template):
    new_state_email = None

    # email_template = inv.env.ref('FAE_app.fae_email_template_invoice', raise_if_not_found=False)
    email_template = inv.env.ref(full_mail_template, raise_if_not_found=False)

    if email_template and inv.partner_id:
        partner_email = inv.partner_id.email
        if not partner_email:
            new_state_email = 'SC'
        else:
            attachment = inv.env['ir.attachment'].search([('res_model', '=', inv._name),
                                                           ('res_id', '=', inv.id),
                                                           ('res_field', '=', 'x_xml_comprobante')],
                                                          order='id desc', limit=1)
            if attachment:
                attachment.name = inv.x_xml_comprobante_fname
                attachment_resp = inv.env['ir.attachment'].search([('res_model', '=', inv._name),
                                                                    ('res_id', '=', inv.id),
                                                                    ('res_field', '=', 'x_xml_respuesta')],
                                                                   order='id desc', limit=1)
                if attachment_resp:
                    attachment_resp.name = inv.x_xml_respuesta_fname
                    email_template.attachment_ids = [(6, 0, [attachment.id, attachment_resp.id])]

                email_template.send_mail(inv.id, force_send=True)
                # 2022-0129: Las siguientes 2 líneas se puso porque odoo hizo una actualización en esta semana
                #            que provocó que se perdieran la asociación de los attachment con los documentos
                attachment.write({'res_model': inv._name, 'res_id': inv.id})
                if attachment_resp:
                    attachment_resp.write({'res_model': inv._name, 'res_id': inv.id})
                # << fin del parche por actualización
                new_state_email = 'E'
            else:
                raise UserError('XML del documento no ha sido generado')
    return new_state_email

# Devuelve el Tag (nodo) solicitado
def getElementTag(xmldoc, tag_name):
    xml_tag = xmldoc.getElementsByTagName(tag_name)
    if xml_tag:
        xml_tag = xml_tag[0]
    return xml_tag

# Devuelve el data de un Tag obtenido con el metodo: getElementsByTagName
def getElementTag_data(xmlTag):
    data = None
    if xmlTag and xmlTag[0].childNodes:
        data = xmlTag[0].childNodes[0].data
    return data
