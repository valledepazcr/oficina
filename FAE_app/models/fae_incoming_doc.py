# -*- coding: utf-8 -*-

from odoo import api, fields, models, tools, _
from odoo.exceptions import Warning, UserError, ValidationError

import email
from email.parser import Parser
from email.header import decode_header
import base64
import datetime, time
from . import fae_utiles

from xml.dom import minidom


from xmlrpc import client as xmlrpclib

import logging

_logger = logging.getLogger(__name__)

# almacena datos de correos que no fallaron al momento de procesarlo
class XFaeIncomingEmail(models.Model):
    _name = "xfae.incoming.email"
    _description = "Correos que no pudieron procesarse"
    _order = "id desc"


    email_account_id = fields.Many2one("xfae.mail", string="Correo Recibe")
    sender = fields.Char(string='Emisor')
    subject = fields.Char(string='Asunto')
    date = fields.Datetime(string='Fecha')



# Almacena los XML que fueron rechazados por hacienda y enviados otros vez luego de corregirse la razon de rechazo
class XFaeIncomingDocRejected(models.Model):
    _name = "xfae.incoming.documents.rejected"
    _description = "Documentos de aceptación que fueron rechazados por la DGT"

    incoming_doc_id = fields.Many2one("xfae.incoming.documents", string="Documento Recibido")
    code_accept = fields.Selection(string='Código Aceptación', 
                                    selection=[('A', 'Aceptado'),
                                              ('P', 'Parcial'),
                                              ('R', 'Rechazado'),
                                              ('AA','Auto-Aceptado')  ], )
    motive_accept = fields.Char(string='Motivo código aceptación', size=160, )  

    currency_id = fields.Many2one('res.currency', string='Moneda')
    tax_use_code_id = fields.Many2one("xtax.use.code", string="Cód.Uso Impuesto", ) 
    amount_tax_credit = fields.Monetary(string="Imp.acreditable",
                                        help='Parte del impuesto que se reportará como crédito fical en la declaración de impuesto', )
    amount_tax_expenses = fields.Monetary(string="Imp.Gasto",
                                        help='Parte del impuesto que será pasado por gasto', )
    sequence = fields.Char(string="Consecutivo acepta", required=False, readonly=True)
    message_accept_xml = fields.Binary(string='XML aceptación', attachment=True, store=True)

    send_date = fields.Date(string='Fecha envio')
    state_response_dgt = fields.Selection(string="Respuesta DGT", copy=False, selection=[('PRO', 'Procesando'),
                                                                                      ('1', 'Aceptado'),
                                                                                      ('2', 'Rechazado') ])
    response_date = fields.Date(string="Fecha Respuesta", required=False)
    message_response_xml = fields.Binary(string='Mensaje de Respuesta XML', attachment=True, store=True)    



class XFaeIncomingDoc(models.Model):
    _name = "xfae.incoming.documents"
    _description = "Documentos de recibidos de proveedores"
    _rec_name = "issuer_sequence"
    _order = "bill_date desc, identification_number, issuer_identification_num"


    identification_type_id = fields.Many2one('xidentification.type', string='Tipo Identificación', )
    identification_number = fields.Char(string='Id Receptor', size=20)
    company_id = fields.Many2one('res.company', string='Company')

    issuer_identification_type = fields.Char(string='Tipo Id.Emisor', size=2)
    issuer_identification_type_id =  fields.Many2one('xidentification.type', string='Tipo Id. Emisor', )
    issuer_identification_num = fields.Char(string='Id Emisor', size=20)
    issuer_name = fields.Char(string='Nombre Emisor', size=400)
    bill_date = fields.Date(string='Fecha Emisión')
    document_type = fields.Selection(string="Tipo Comprobante",
                                        selection=[('FE', 'Factura Electrónica'),
                                                   ('TE', 'Tiquete Electrónico'),
                                                   ('FEE', 'Factura Electrónica de Exportación'),
                                                   ('ND', 'Nota de Débito'),
                                                   ('NC', 'Nota de Crédito'),
                                                   ('FEC', 'Factura Electrónica de Compra')],
                                        required=False, default='FE', )
    issuer_sequence = fields.Char(string='Número Documento', size=20)
    issuer_electronic_code50 = fields.Char(string='Clave Hacienda', size=50)
    issuer_xml_doc = fields.Binary(string='Documento Electrónico XML', attachment=True, store=True)
    issuer_xml_response = fields.Binary(string='Respuesta Hacienda XML', attachment=True, store=True)
    issuer_pdf = fields.Binary(string='Issuer PDF', attachment=True, store=True)
    quantity_xmls = fields.Integer(string='Cantidad XML')
    
    # move_id = fields.Many2one("account.move", string="Factura", required=False)

    include_tax_tag = fields.Boolean(string='Impuestos', default=False)
    #  currency = fields.Char(string='Currency')
    currency_id = fields.Many2one('res.currency', string='Moneda')
    amount_tax = fields.Monetary(string='Amount Tax')
    amount_total = fields.Monetary(string='Amount Total')

    response_state = fields.Selection(string='Respuesta a Emisor',
                                        selection=[('1', 'Aceptado'),
                                                    ('2', 'Rechazado')],
                                        default=None, )

    message_xml = fields.Binary(string='Mensaje XML', attachment=True, store=True)

    message_send_date = fields.Date(string="Fecha Envío", required=False)
    quantity_messages = fields.Integer(string='Cantidad Mensaje XML')
    origin = fields.Char(string='Origen', default='mail')
    email_account_id = fields.Many2one("xfae.mail", string="Cuenta Correo Recibe", )

    # necesito el tener issuer_xml_doc para A, P, o R
    code_accept = fields.Selection(string='Código Aceptación', 
                                    selection=[('A', 'Aceptado'),
                                              ('P', 'Parcial'),
                                              ('R', 'Rechazado'),
                                              ('D', 'Descartado'),
                                              ('AA','Auto-Aceptado') ],
                                    default=None, )
    # motive_code_accept = fields.Char(string='Motivo código aceptación', size=160, )  
    motive_accept = fields.Char(string='Motivo código aceptación', size=160, )  

    tax_use_code_id = fields.Many2one("xtax.use.code", string="Cód.Uso Impuesto", )    
    amount_tax_credit = fields.Monetary(string="Imp.acreditable",
                                        help='Parte del impuesto que se reportará como crédito fical en la declaración de impuesto', )
    amount_tax_expenses = fields.Monetary(string="Imp.Gasto",
                                        help='Parte del impuesto que será pasado por gasto', )
    
    sequence = fields.Char(string="Consecutivo aceptación", required=False, readonly=True)
    count_accept = fields.Integer(string="Veces enviado", copy=False, default=0, )
    message_accept_xml = fields.Binary(string='XML aceptación', attachment=True, store=True)
    # message_accept_xml_fname = fields.Char(string="Nombre archivo XML Aceptación", required=False, copy=False )


    send_date = fields.Datetime(string='Fecha envio')

    # Estos valores deben poderse asignar a "account.move.x_state_dgt"
    state_response_dgt = fields.Selection(string="Respuesta DGT", copy=False, selection=[('PRO', 'Procesando'),
                                                                                      ('1', 'Aceptado'),
                                                                                      ('2', 'Rechazado') ])
    response_date = fields.Datetime(string="Fecha Respuesta", required=False)
    message_response_xml = fields.Binary(string='Mensaje de Respuesta XML', attachment=True, store=True)
    # message_response_xml_fname = fields.Char(string="Nombre archivo Respuesta DGT", required=False, copy=False )


    message_response = fields.Char(string='Mensaje Respuesta')

    documents_rejected = fields.One2many(string='Documentos Rechazados',
                                         comodel_name='xfae.incoming.documents.rejected',
                                         inverse_name='incoming_doc_id',
                                         copy=True, )

    ready2accounting = fields.Boolean(string='Contabilizable', copy=False, default=False,
                                        help='Habilita el documento para que pueda ser ingresado Cuentas por Pagar')

    # campo para almacenar el ID del invoice que utilizó este documento
    invoice_id = fields.Integer(string="Invoice ID", copy=False, 
                                help="Este campo es solo para almacenar el ID del invoice que lo utilizó")
    purchase_registried = fields.Boolean(string='Bill Contabilizado', default=False,
                                help='Indica si el documento ya fue ingresado en compras' )    

    _sql_constraints = [('issuer_electronic_code50_uniq', 'unique (issuer_electronic_code50, company_id)',
                        "La clave numérica deben ser única"),
                        ]

    # def init(self):
    #     name_index = self._table + '_company_' + 
    #     self._cr.execute("""SELECT indexname FROM pg_indexes WHERE indexname = 'studio_approval_entry_model_res_id_idx'""")
    #     if not self._cr.fetchone():
    #         self._cr.execute("""CREATE INDEX studio_approval_entry_model_res_id_idx ON studio_approval_entry (model, res_id)""")

    @api.model
    def create(self, vals):
        res = super(XFaeIncomingDoc, self).create(vals)
        return res

    def write(self, vals):
        res = super(XFaeIncomingDoc, self).write(vals) 
        code_accept = vals.get('code_accept')
        state_response_dgt = vals.get('state_response_dgt')

    def unlink(self):
        for rec in self:
            if rec.code_accept:
                raise ValidationError('El documento: %s ya tiene aceptación' % (rec.issuer_sequence))
            elif rec.invoice_id:
                raise ValidationError('El documento: %s ya está asociado con documento ingresado en Proveedor' % (rec.issuer_sequence))
        return super(XFaeIncomingDoc, self).unlink()

    @api.model
    def search_read(self, domain=None, fields=None, offset=0, limit=None, order=None):
        aux = ['|', ('company_id', 'in', self.env.companies.ids), ('company_id', '=', False)]

        for a in aux:
            domain.append(a)

        res = super(XFaeIncomingDoc, self).search_read(domain, fields, offset, limit, order)
        return res

    @api.onchange('code_accept')
    def _onchange_code_accept(self):
        if self.code_accept in ('A','P','R','AA'):
            if not self.company_id:
                raise Warning('La cédula del receptor no corresponde a alguna de las compañías instaladas')
            elif not self.issuer_xml_doc:
                raise Warning('No puede Aceptar o Rechazar el documento debido a que no tiene el documento electrónico adjunto (XML)')

    @api.onchange('tax_use_code_id')
    def _onchange_tax_use_id(self):
        if not self.tax_use_code_id or self.tax_use_code_id.code == '05':
            self.amount_tax_credit = 0
            self.amount_tax_expenses = 0
        else:
            total = (self.amount_tax_credit or 0) + (self.amount_tax_expenses or 0)
            if self.tax_use_code_id.code == '01' and total == 0:
                self.amount_tax_credit = round(self.amount_tax,4)

    @api.onchange('amount_tax_credit', 'amount_tax_expenses')
    def _onchange_amount_tax_use(self):
        total = 0        
        if not self.amount_tax_expenses or self.amount_tax_expenses < 0:
            self.amount_tax_expenses = 0
        if not self.amount_tax_credit or self.amount_tax_credit < 0:
            self.amount_tax_credit = 0
        total = round(self.amount_tax_credit + self.amount_tax_expenses,4)
        if total > (self.amount_tax or 0):
            raise Warning('El total impuestos acreditados no puede ser mayor al impuesto pagado' )

    # descarga los documentos recibidos en el correo
    def read_email(self):
        fae_email = self.env['xfae.mail'].search([('type', '=', 'in')])
        identification_types = self.env['xidentification.type'].search([])
        companies = self.env['res.company'].search([])
        currencies = self.env['res.currency'].search([('name', 'in', ['CRC', 'USD'])])

        failed = 0

        # >> método interno
        def procesa_correo(email_account_id, num, message):
            """ like Mail_thread.message_process
            Process an incoming RFC2822 email message
            """
            nonlocal failed
            msg_dict = {}
            try:
                # extract message bytes - we are forced to pass the message as binary because
                # we don't know its encoding until we parse its headers and hence can't
                # convert it to utf-8 for transport between the mailgate script and here.
                MailThread = self.env['mail.thread']
                if isinstance(message, xmlrpclib.Binary):
                    message = bytes(message.data)
                if isinstance(message, str):
                    message = message.encode('utf-8')
                message = email.message_from_bytes(message, policy=email.policy.SMTP)

                msg_dict = MailThread.message_parse(message, save_original=False)
                _logger.info('>>   fae_incoming_doc.read_email: num: %s  From: %s  - Subject: %s', num,  msg_dict.get('email_from'), msg_dict.get('subject'))
                attachments = msg_dict.pop('attachments', None)
                if attachments:
                    complete_vals = {}
                    flag2save = True
                    attach_pdf = None
                    clave_hacienda = None
                    for a in attachments:
                        if a.fname:
                            file_name = a.fname.lower()
                            attach_xml = None
                            if file_name.find('.xml') > 0:
                                attach_xml = a.content
                                inicio_xml = '<?xml' if isinstance(attach_xml, str) else b'<?xml'
                                i = attach_xml.find(inicio_xml)
                                if i > 0:
                                    # se detectaron problemas con xml que traian caracteres extraños al inicio
                                    attach_xml = attach_xml[i:]
                            elif file_name.find('.pdf') > 0:
                                attach_pdf = a.content

                            # _logger.info('>> fae_incoming_doc.read_email/pop:    attach_xml: %s', str(attach_xml))
                            if attach_xml:
                                values = fae_utiles.parser_xml(identification_types, companies, currencies, 'email', attach_xml)
                                clave_xml = values.get('issuer_electronic_code50')
                                # _logger.info('>> fae_incoming_doc.read_email/pop:    despues parser xml declave_xml: %s', clave_xml)
                                if clave_hacienda and clave_xml:
                                    if clave_hacienda != clave_xml:
                                        flag2save = False
                                elif clave_xml:
                                    clave_hacienda = clave_xml
                                complete_vals.update(values)

                    if clave_hacienda and flag2save:
                        complete_vals.update({'email_account_id': server.id})
                        # _logger.info('>> fae_incoming_doc.read_email/pop:    antes de save_incoming document')
                        res = self.save_incoming_document(clave_hacienda, complete_vals, attach_pdf)

            except Exception as e:
                if msg_dict:
                    incoming_email = self.env['xfae.incoming.email']
                    values = {'email_account_id': email_account_id,
                              'sender': msg_dict.get('email_from'),
                              'subject': msg_dict.get('subject'),
                              'date': msg_dict.get('date')
                             }
                    incoming_email.sudo().create(values)
                _logger.error('>> fae_incoming_doc.read_email: Exception al procesar correo num: %s  from: %s   Err: %s',
                              str(num), msg_dict.get('email_from'), tools.ustr(e))
                failed += 1
        #<< Fin de métodos internos

        for server in fae_email:
            _logger.info('>> fae_incoming_doc.read_email: Cuenta: %s   - Servidor: %s ', server.name, server.server)
            email_server = None
            failed = 0
            try:
                if server.server_type == 'imap':
                    try:
                        email_server = server.connect()
                        email_server.select()
                        result, data = email_server.search(None, '(UNSEEN)')

                        unseen_count = data[0].split()
                        _logger.info('>> fae_incoming_doc.read_email/imap:  Cantidad de correos: %s', str(unseen_count) )
                        for num in unseen_count:
                            try:
                                result, data = email_server.fetch(num, '(RFC822)')
                                email_server.store(num, '-FLAGS', '\\Seen')
                                procesa_correo(server.id, num, data[0][1])
                            except Exception as e:
                                _logger.error('>> fae_incoming_doc.read_email/pop: Exception traer correo num: %s   Err: %s', str(num), tools.ustr(e)[:320])
                                failed += 1
                            email_server.store(num, '+FLAGS', '\\Seen')
                            self._cr.commit()
                    except Exception:
                        _logger.info('>> fae_incoming_doc.read_email: Fallo tratando de hacer un fetch: %s  server %s', server.server_type, server.name, exc_info=True)
                    finally:
                        if email_server:
                            email_server.close()
                            email_server.logout()

                elif server.server_type == 'pop':
                    try:
                        email_server = server.connect()
                        # stat() function return email count and occupied disk size
                        (messageCount, totalMessageSize) = email_server.stat()
                        email_server.list()  # return all email list

                        _logger.info('>> fae_incoming_doc.read_email/pop:  Cantidad de correos: %s', str(messageCount))
                        for num in range(messageCount, 0, -1):
                            try:
                                (header, messages, octets) = email_server.retr(num)
                                message = (b'\n').join(messages)
                                procesa_correo(server.id, num, message)
                            except Exception as e:
                                _logger.error('>> fae_incoming_doc.read_email/pop: Exception traer correo num: %s   Err: %s', str(num), tools.ustr(e)[:320])
                                failed += 1
                            self._cr.commit()
                    except Exception:
                        _logger.info('>> fae_incoming_doc.read_email: Fallo tratando de hacer un fetch: %s  server %s', server.server_type, server.name,
                                     exc_info=True)
                    finally:
                        if email_server:
                            email_server.quit()
            except Exception as e:
                _logger.info('>>   fae_incoming_doc.read_email: Exception: %s', tools.ustr(e)[:320] )

            if failed > 0:
                _logger.info('>>   fae_incoming_doc.read_email: Cuenta: %s,  No se pudo procesar: %s correos ', server.name, str(failed))

        # ---
        # revisa si hay documento que ya pueden contabilizarse porque están pasado
        fref = datetime.datetime.today() - datetime.timedelta(days=28)  # devuelve al mes anterior
        fref = datetime.datetime(fref.year, fref.month, 11)  # aproximadamente 10 días habiles
        date_str = fref.strftime('%Y-%m-%d')
        # _logger.info('>> fae_incoming_doc.read_email: date_str %s', date_str )
        documents = self.env['xfae.incoming.documents'].search([('bill_date', '<', date_str), ('ready2accounting', '=', False), ('code_accept', '=', False)])
        for rec in documents:
            if rec.company_id:
                rec.code_accept = 'AA'
                rec.ready2accounting = True

        return True

    def save_incoming_document(self, clave_hacienda, complete_vals, pdf_doc):
        if clave_hacienda and complete_vals:
            ind_xml_doc = 1 if complete_vals.get('issuer_xml_doc') else 0
            ind_xml_resp = 1 if complete_vals.get('issuer_xml_response') else 0

            incoming_document = self.env['xfae.incoming.documents'].search([('issuer_electronic_code50', '=', clave_hacienda)], limit=1)
            flag2save = True
            if incoming_document:
                # el documento existe, si ya fue enviado a hacienda entonces no guarda los datos
                if incoming_document.code_accept or incoming_document.state_response_dgt:
                    flag2save = False
                else:
                    if ind_xml_doc == 0 and incoming_document.issuer_xml_doc:
                        ind_xml_doc = 1
                    if ind_xml_resp == 0 and incoming_document.issuer_xml_response:
                        ind_xml_resp = 1

            if flag2save and clave_hacienda:
                if pdf_doc:
                    pdf = base64.encodebytes(pdf_doc)
                    vals = {'issuer_pdf': pdf,
                            'quantity_xmls': (ind_xml_doc + ind_xml_resp), }
                else:
                    vals = {'quantity_xmls': (ind_xml_doc + ind_xml_resp), }

                complete_vals.update(vals)

                if incoming_document:
                    incoming_document.write(complete_vals)
                else:
                    res = self.env['xfae.incoming.documents'].sudo().create(complete_vals)
        return True

    def create_doc_rejected(self, incoming_documents):
        for doc in incoming_documents:
            values = {
                'incoming_doc_id': doc.id,
                'currency_id': doc.currency_id.id,
                'code_accept': doc.code_accept,
                'motive_accept': doc.motive_accept,
                'tax_use_code_id': doc.tax_use_code_id.id,
                'amount_tax_credit': doc.amount_tax_credit,
                'amount_tax_expenses': doc.amount_tax_expenses,
                'sequence': doc.sequence,
                'message_accept_xml': doc.message_accept_xml,
                'send_date': doc.send_date,
                'state_response_dgt': doc.state_response_dgt,
                'response_date': doc.response_date,
                'message_response_xml': doc.message_response_xml,                
            }
            res = self.env['xfae.incoming.documents.rejected'].sudo().create(values)

    def action_send_aceptacion(self):  
        self.write({})
        count_doc = 0
        for doc in self:
            if self.code_accept in ('A', 'P', 'R') and (not self.state_response_dgt or self.state_response_dgt != '1'):
                count_doc += 1
        if count_doc > 0:
            self.generate_xml_and_send_dgt()

    # Generate Message XML de Aceptacion o Rechazo
    def generate_xml_and_send_dgt(self):
        count_doc = 0
        for doc in self:
            if doc.company_id.x_fae_mode != 'api-prod':
                raise Warning('No se puede aceptar documentos si la compañía esta configurada en modo de envio: PRUEBAS')
                continue
            if doc.state_response_dgt and doc.state_response_dgt == '1':
                continue

            if (doc.company_id.x_fae_mode == 'api-prod' and doc.company_id.x_prod_expire_date <= datetime.date.today() ):
                raise UserError('La llave criptográfica está vencida, debe actualizarse con una más reciente')
            
            count_doc += 1
            consecutivo = doc.sequence
            if doc.sequence:
                # el documento ya tenia numero por lo que lo guarda en rechazados
                self.create_doc_rejected(self)
                doc.message_accept_xml = None

            if doc.code_accept == 'A':
                consecutivo = doc.company_id.x_sequence_MRA_id.next_by_id()
            elif doc.code_accept == 'P':
                consecutivo = doc.company_id.x_sequence_MRP_id.next_by_id()
            elif doc.code_accept == 'R':
                consecutivo = doc.company_id.x_sequence_MRR_id.next_by_id()
            else:
                raise UserError('El tipo de documento de aceptación: %s no es válido' % (doc.code_accept) )
            doc.sequence = fae_utiles.gen_consecutivo(doc.code_accept, consecutivo, doc.company_id.x_sucursal, doc.company_id.x_terminal)
            doc.send_date = datetime.datetime.today()   ## requerida para enviar el xml a hacienda

            if not doc.message_accept_xml:
                try:
                    xml_str = fae_utiles.gen_xml_approval(doc)
                except Exception as error:
                    raise Exception('Falla ejecutando fae_utiles.gen_xml_approval, error: %s' % (str(error)) )

                try:
                    xml_firmado = fae_utiles.sign_xml(doc.company_id.x_prod_crypto_key, doc.company_id.x_prod_pin, xml_str)

                    doc.message_accept_xml = base64.encodebytes(xml_firmado)
                except Exception as error:
                    raise Exception('Falla ejecutando fae_utiles.sign_xml, error: %s' % (str(error)) )

                # envia el XML firmado
                response_json = fae_utiles.send_xml_acepta_rechazo(doc,  xml_firmado, doc.company_id.x_fae_mode)                
                response_status = response_json.get('status')
                response_text = response_json.get('text')
                                
                if 200 <= response_status <= 299:
                    doc.state_response_dgt = 'PRO'

        # Si envio documentos, entonces espera unos segundos antes de empezar a consultar por el status
        if count_doc > 0:
            time.sleep(15)  # espera 
            self.consulta_status_mar_enviados(self)

        return True

    # Consulta Mensaje de respuestas cron Job: Chequea en hacienda el status de documentos de clientnes enviados
    def _check_status_mar_enviados(self, max_docs=20):
        if not self.company_id.x_fae_mode or self.company_id.x_fae_mode == 'N':
            return        
        documents = self.env['xfae.incoming.documents'].search(
                                        [('state_response_dgt', '=', 'PRO')], 
                                        limit=max_docs)
        if len(documents) > 0:
            self.consulta_status_mar_enviados(documents)

    def consulta_status_doc_enviado(self):
        if not self.company_id.x_fae_mode or self.company_id.x_fae_mode == 'N':
            return 
        self.consulta_status_mar_enviados(self)

    # consulta el status del mensaje de aceptación o rechazo enviado a la dgt
    def consulta_status_mar_enviados(self, documents):

        # Invoices recibido de proveedores
        for doc in documents:
            if doc.state_response_dgt != 'PRO':
                continue

            token_dgt = fae_utiles.get_token_hacienda(doc.company_id, doc.company_id.x_fae_mode)
         
            # consulta el estado de la clave en hacienda
            response_json = fae_utiles.consulta_clave(doc.issuer_electronic_code50 + '-' + doc.sequence
                                                    ,token_dgt
                                                    ,doc.company_id.x_fae_mode)
            status = response_json['status']

            ind_estado =''
            if status in (200, 400):
                ind_estado = response_json.get('ind-estado')
                ind_estado = ind_estado.lower()
            else:
                status = -1
            
            if status != 200:
                _logger.error('>> consulta_status_mar_enviado: Error de status para Doc %s, status: %s', doc.issuer_sequence, str(status) )
                continue

            if ind_estado in ('aceptado', 'firma_invalida', 'rechazado'):
                doc.response_date = datetime.datetime.today()
                doc.message_response_xml = response_json.get('respuesta-xml')
                if ind_estado == 'aceptado':
                    doc.state_response_dgt = '1'
                    doc.ready2accounting = True
                    doc.message_response = None
                else:
                    doc.state_response_dgt = '2'

                if doc.message_response_xml:
                    try:
                        xml_doc = minidom.parseString(doc.message_response_xml)
                        mensaje = xml_doc.getElementsByTagName('Mensaje')[0].childNodes[0].data
                        doc.message_response = xml_doc.getElementsByTagName('DetalleMensaje')[0].childNodes[0].data
                    except Exception as e:
                        _logger.error('>> consulta_status_mar_enviado: try exception to getElementTag, Doc %s, status: %s', doc.issuer_sequence, str(status) )


    #  read_email anterior al 26-oct-2021
    def read_email_ant_oct2021(self):
        self.read_email2v()
        return

        _logger.info('>> fae_incoming_doc.read_email: Inicio ')
        fae_email = self.env['xfae.mail'].search([('type', '=', 'in')])
        identification_types = self.env['xidentification.type'].search([])
        companies = self.env['res.company'].search([])
        currencies = self.env['res.currency'].search([('name', 'in', ['CRC', 'USD'])])

        for server in fae_email:
            _logger.info('>> fae_incoming_doc.read_email: Cuenta: %s   - Servidor: %s ', server.name, server.server)
            try:
                connection = server.connect()
                server.write({'state': 'done'})

                if server.server_type == 'imap':
                    num_Messages = len(connection.list()[1])
                    status, messages = connection.select("INBOX")
                    unseen_count = len(connection.search(None, 'UnSeen')[1][0].split())  # search(None, '(UNSEEN)')
                    messages = int(messages[0])

                    _logger.info('>> fae_incoming_doc.read_email/imap:  Cantidad de correos: %s', str(unseen_count))

                    for num in range(messages, messages - unseen_count, -1):
                        try:
                            res, msg = connection.fetch(str(num), "(RFC822)")
                            for response in msg:
                                if not isinstance(response, tuple):
                                    continue

                                msg = email.message_from_bytes(response[1])
                                # _logger.info('>> fae_incoming_doc.read_email/imap: num: %s', str(num) )
                                if msg.is_multipart():
                                    complete_vals = {}
                                    flag2save = True
                                    attach_pdf = None
                                    clave_hacienda = None

                                    for part in msg.walk():
                                        content_type = part.get_content_type()
                                        content_disposition = str(part.get("Content-Disposition"))

                                        _logger.info('>> fae_incoming_doc.read_email/imap: num: %s  From: %s  - Subject: ', num, part.get('From'),
                                                     part.get('Subject'))

                                        if content_type == "application/xml" or content_type == 'text/xml' or content_type == 'application/octet-stream':
                                            file_name = part.get_filename()
                                            if file_name:
                                                attach_xml = part.get_payload(decode=True)
                                                values = fae_utiles.parser_xml(identification_types, companies, currencies, 'email', attach_xml)

                                                clave_xml = values.get('issuer_electronic_code50')
                                                if clave_hacienda and clave_xml:
                                                    if clave_hacienda != clave_xml:
                                                        flag2save = False
                                                elif clave_xml:
                                                    clave_hacienda = clave_xml

                                                if complete_vals:
                                                    complete_vals.update(values)
                                                else:
                                                    complete_vals = values

                                        if content_type == "application/pdf":
                                            file_name = part.get_filename()
                                            if file_name:
                                                attach_pdf = part.get_payload(decode=True)

                                    if clave_hacienda and flag2save:
                                        complete_vals.update({'email_account_id': server.id})
                                        res = self.save_incoming_document(clave_hacienda, complete_vals, attach_pdf)
                        except Exception as e:
                            _logger.error('>> fae_incoming_doc.read_email/imap: Exception al procesar correo num: %s   Err: %s', str(num), tools.ustr(e))
                    connection.close()


                elif server.server_type == 'pop':
                    # stat() function return email count and occupied disk size
                    (messageCount, totalMessageSize) = connection.stat()
                    # list() function return all email list
                    connection.list()

                    _logger.info('>> fae_incoming_doc.read_email/pop:  Cantidad de correos: %s', str(messageCount))
                    for num in range(messageCount, 0, -1):
                        try:
                            (header, messages, octets) = connection.retr(num)
                            message = (b'\n').join(messages).decode('utf-8')

                            msg = Parser().parsestr(message)
                            subject = msg.get('Subject')
                            # _logger.info('>> fae_incoming_doc.read_email/pop: procesando correo num: %s  - from : %s  subject: %s', str(num), msg.get('From'), subject )
                            asunto, charset = decode_header(subject)[0]
                            if charset:
                                asunto = asunto.decode(charset)
                            # _logger.info('>> fae_incoming_doc.read_email/pop: procesando correo num: %s  - from : %s  Asunto: %s', str(num), msg.get('From'), asunto )

                            if (msg.is_multipart()):
                                complete_vals = {}
                                flag2save = True
                                attach_pdf = None
                                clave_hacienda = None
                                parts = msg.get_payload()

                                for n, part in enumerate(parts):
                                    content_type = part.get_content_type()
                                    file_name = part.get_filename()

                                    if file_name:
                                        file_name = file_name.lower()
                                        attach_xml = None

                                        if content_type == "application/xml" or content_type == "text/xml":
                                            attach_xml = part.get_payload(decode=True)
                                        elif content_type == 'application/octet-stream' and file_name.find('.xml') >= 0:
                                            attach_xml = part.get_payload(decode=True)

                                        # _logger.info('>> fae_incoming_doc.read_email/pop:    attach_xml: %s', str(attach_xml))
                                        if attach_xml:
                                            values = fae_utiles.parser_xml(identification_types, companies, currencies, 'email', attach_xml)
                                            clave_xml = values.get('issuer_electronic_code50')
                                            # _logger.info('>> fae_incoming_doc.read_email/pop:    despues parser xml declave_xml: %s', clave_xml)
                                            if clave_hacienda and clave_xml:
                                                if clave_hacienda != clave_xml:
                                                    flag2save = False
                                            elif clave_xml:
                                                clave_hacienda = clave_xml

                                            if complete_vals:
                                                complete_vals.update(values)
                                            else:
                                                complete_vals = values

                                        if content_type == "application/pdf" or (content_type == 'application/octet-stream' and file_name.find('.pdf') >= 0):
                                            # _logger.info('>> fae_incoming_doc.read_email/pop:    antes de get_payload PDF')
                                            attach_pdf = part.get_payload(decode=True)

                                if clave_hacienda and flag2save:
                                    complete_vals.update({'email_account_id': server.id})
                                    # _logger.info('>> fae_incoming_doc.read_email/pop:    antes de save_incoming document')
                                    res = self.save_incoming_document(clave_hacienda, complete_vals, attach_pdf)
                        except Exception as e:
                            _logger.error('>> fae_incoming_doc.read_email/pop: Exception al procesar correo num: %s   Err: %s', str(num), tools.ustr(e))
                    connection.quit()


            except Exception as err:
                _logger.error('>> fae_incoming_doc.read_email: Exception al procesar las cuentas de correos. Err: %s', tools.ustr(err))

        # ---
        # revisa si hay documento que ya pueden contabilizarse porque están pasado
        fref = datetime.datetime.today() - datetime.timedelta(days=28)  # devuelve al mes anterior
        fref = datetime.datetime(fref.year, fref.month, 11)  # aproximadamente 10 días habiles
        date_str = fref.strftime('%Y-%m-%d')
        # _logger.info('>> fae_incoming_doc.read_email: date_str %s', date_str )
        documents = self.env['xfae.incoming.documents'].search([('bill_date', '<', date_str), ('ready2accounting', '=', False), ('code_accept', '=', False)])
        for rec in documents:
            # company = companies.filtered(lambda c: c.vat == rec.identification_number)
            # if company:
            if rec.company_id:
                rec.code_accept = 'AA'
                rec.ready2accounting = True

        return True