from odoo import models, fields, api, _

from xml.sax.saxutils import escape
import base64
import datetime
import time
import pytz
import json
# from xml.dom import minidom
from lxml import etree

from . import fae_utiles
from . import fae_enums

from odoo.exceptions import UserError, ValidationError
import logging

_logger = logging.getLogger(__name__)


class AccountMoveReversal(models.TransientModel):
    _inherit = "account.move.reversal"

    def _prepare_default_reversal(self, move):
        reverse_date = self.date if self.date_mode == 'custom' else move.date
        document_type_dest = None
        if move.move_type == 'out_invoice' and move.x_state_dgt not in ('2', 'FI'):
            document_type_dest = 'NC'
        elif move.move_type == 'out_refund' and move.x_state_dgt not in ('2', 'FI'):
            document_type_dest = 'ND'
        
        data =  {
            'ref': _('Reversal of: %(move_name)s, %(reason)s', move_name=move.name, reason=self.reason)
                   if self.reason
                   else _('Reversal of: %s', move.name),
            'date': reverse_date,
            'invoice_date': move.is_invoice(include_receipts=True) and (self.date or move.date) or False,
            'journal_id': self.journal_id and self.journal_id.id or move.journal_id.id,
            'invoice_payment_term_id': None,
            'invoice_user_id': move.invoice_user_id.id,
            'auto_post': True if reverse_date > fields.Date.context_today(self) else False,
            }

        data['x_document_type'] = document_type_dest
        if document_type_dest:
            rec_reference_code = self.env['xreference.code'].search([('code', '=', '01')], limit=1)
            ref_docum_code = fae_enums.tipo_doc_num.get(move.x_document_type) 
            rec_reference_document_type = False
            if ref_docum_code:
                rec_reference_document_type = self.env['xreference.document'].search([('code','=',ref_docum_code)], limit=1)                
            data['x_economic_activity_id'] = move.x_economic_activity_id.id
            data['x_payment_method_id'] = move.x_payment_method_id.id
            data['x_reference_code_id'] = rec_reference_code.id
            data['x_invoice_reference_id'] = move.id
            data['x_reference_document_type_id'] = rec_reference_document_type.id

        return data


class FaeAccountInvoiceLine(models.Model):
    _inherit = "account.move.line"

    x_product_code = fields.Char(related='product_id.default_code',)

    x_discount_note = fields.Char(string="Nota de descuento", size=80, required=False, )
    x_total_tax = fields.Monetary(string="Total impuesto", required=False, )

    # x_tariff_heading = fields.Char(string="Partida arancelaria Expo.", required=False, )
    x_other_charge_partner_id = fields.Many2one("res.partner", string="Tercero otros cargos",)
    x_economic_activity_id = fields.Many2one("xeconomic.activity", string="Actividad Económica", required=False,
                                            context={'active_test': False}, )

    @api.onchange('tax_ids')
    def _onchange_tax(self):        
        move = self.move_id
        if not move.is_sale_document():
            return
        for tax in self.tax_ids:
            if tax.x_has_exoneration:
                if not move.partner_id:
                    raise ValidationError('El impuesto: %s es para exoneración pero el documento no le han definido un cliente' % tax.name)
                if move.partner_id.x_special_tax_type != 'E':
                    raise ValidationError('El impuesto: %s es para exoneración pero el cliente no tiene definido que es exonerado' % tax.name)
                if not move.partner_id.property_account_position_id:
                    raise ValidationError('El impuesto: %s es para exoneración pero el cliente no tiene definido la posición fiscal' % tax.name)

    @api.onchange('debit')
    def _onchange_debit(self):
        if len(self) > 1:
            return
        move = self.move_id
        if move.is_sale_document() and not self.exclude_from_invoice_tab and (move.posted_before or move.x_sequence) and self._origin.debit != self.debit:
            raise ValidationError('No se permite modificar el monto para líneas asociadas a líneas del invoice')

    @api.onchange('credit')
    def _onchange_credit(self):
        if len(self) > 1:
            return
        move = self.move_id
        if move.is_sale_document() and not self.exclude_from_invoice_tab and (move.posted_before or move.x_sequence) and self._origin.credit != self.credit:
            raise ValidationError('No se permite modificar el monto para líneas asociadas a líneas del invoice')

    def unlink(self):
        for line in self:
            if line.move_id.is_invoice():
                # invoices (customer o vendors)
                if line.move_id.posted_before and not line.exclude_from_invoice_tab:
                    raise ValidationError('No puede eliminar la línea contable porque está asociada con una línea de la factura')
        return super(FaeAccountInvoiceLine, self).unlink()


class FaeAccountInvoice(models.Model):
    _inherit = "account.move"


    def _default_document_type(self):
        move_type = self.env.context.get('default_move_type', 'entry')
        if move_type in ('out_refund','in_refund'):
            return 'NC'
        elif move_type in ('out_invoice', 'in_invoice'):
            return 'FE'
        else:
            return None

    #
    line_ids = fields.One2many('account.move.line', 'move_id', string='Journal Items', copy=True, readonly=True, )
    x_generated_dgt = fields.Boolean(compute='_compute_x_editable_generated_dgt', readonly=True)
    x_move_editable = fields.Boolean(compute='_compute_x_editable_generated_dgt', readonly=True)
    x_accounting_lock = fields.Boolean(compute='_compute_x_editable_generated_dgt', readonly=True) 

    #
    x_economic_activity_id = fields.Many2one("xeconomic.activity", string="Actividad Económica", required=False,
                                             context={'active_test': True}, )
    x_document_type = fields.Selection(string="Tipo Comprobante",
                                        selection=[('FE', 'Factura Electrónica'),
                                                ('TE', 'Tiquete Electrónico'),
                                                ('FEE', 'Factura de Exportación'),
                                                ('ND', 'Nota de Débito'),
                                                ('NC', 'Nota de Crédito'),
                                                ('FEC', 'Factura de Compra')],
                                        required=False, default=_default_document_type, 
                                        )
    x_sequence = fields.Char(string="Núm.Consecutivo", required=False, readonly=True, copy=False, index=True)
    x_electronic_code50 = fields.Char(string="Clave Numérica", required=False, copy=False, index=True)
    x_issue_date = fields.Char(string="Fecha Emisión", size=(30), required=False, copy=False)

    x_state_dgt = fields.Selection(string="Estado DGT",
                                    copy=False,
                                    selection=[('PRO', 'Procesando'),
                                               ('POS', 'Pendiente en POS'),                                    
                                               ('1', 'Aceptado'),
                                               ('2', 'Rechazado'),
                                               ('FI', 'Firma Inválida'),
                                               ('ERR', 'Error')])

    x_payment_method_id = fields.Many2one("xpayment.method", string="Método de Pago", required=False, copy=True,)
    x_reference_code_id = fields.Many2one("xreference.code", string="Cod.Motivo referencia", required=False, copy=False, )
    x_invoice_reference_id = fields.Many2one("account.move", string="Doc.Referencia", required=False, copy=False)
    x_reference_document_type_id = fields.Many2one("xreference.document", string="Tipo Doc.Referencia", required=False, )
    x_is_external_reference = fields.Boolean(string="Documento Externo", required=False, default=False,
                                            help='Indica el documento referenciado no fue generado en Odoo, proviene de otro sistema o de un proveedor', )
    x_ext_reference_num = fields.Char(string="Numero Referencia",
                                        help='Número de Documento o Clave numérica de 50 dígitos, del documento referenciado')
    x_ext_reference_date = fields.Date(string="Fecha Documento")
    x_ext_reference_razon = fields.Char(string="Motivo Referencia", size=180)

    x_xml_comprobante = fields.Binary(string="XML documento", required=False, copy=False, attachment=True )
    x_xml_comprobante_fname = fields.Char(string="Nombre archivo Comprobante XML", required=False, copy=False )
    x_xml_respuesta = fields.Binary(string="XML Respuesta", required=False, copy=False, attachment=True )
    x_xml_respuesta_fname = fields.Char(string="Nombre archivo Respuesta DGT", required=False, copy=False )

    x_amount_tax = fields.Monetary(string='Impuestos', readonly=True, )
    x_amount_total = fields.Monetary(string='Total', readonly=True, )
    x_currency_rate = fields.Float(string="Tipo Cambio", required=False, copy=False)
    x_response_date = fields.Datetime(string="Fecha Respuesta", required=False, copy=False)
    x_mensaje_respuesta = fields.Char(string="Mensaje Respuesta", copy=False)

    x_error_count = fields.Integer(string="Cant Errores DGT", copy=False, required=False, default=0 )

    x_state_email = fields.Selection(string="Estado Email",
                                     selection=[('SC', 'Sin cuenta de correo'),
                                                ('E', 'Enviado'),
                                                ('NOE', 'No Envia')],
                                     copy=False)
    #
    x_show_reset_to_draft_button = fields.Boolean(compute='_compute_x_show_reset_to_draft_button')
    x_show_generate_xml_button = fields.Boolean(compute='_compute_x_show_generate_xml_button')

    x_partner_vat = fields.Char(related='partner_id.vat')
    x_fae_incoming_doc_id = fields.Many2one("xfae.incoming.documents", string="Doc.Electrónico",
                                        required=False, 
                                        domain="[('document_type','=',x_document_type),('issuer_identification_num','=',x_partner_vat),('ready2accounting','=',True),('invoice_id','=',False)]",
                                        )

    _sql_constraints = [('x_electronic_code50_uniq', 'unique (company_id, x_electronic_code50)',
                        "La clave numérica deben ser única"), ]

    def unlink(self):
        for rec in self:
            if rec.x_accounting_lock:
                raise ValidationError('La contabilidad está cerrada a la fecha del movimiento: %s' % rec.name)
        return super(FaeAccountInvoice, self).unlink()


    @api.depends('state', 'x_sequence')
    def _compute_x_editable_generated_dgt(self):
        for rec in self:
            rec.x_generated_dgt = rec.is_invoice() and (rec.x_sequence or rec.x_state_dgt) 
            rec.x_move_editable = (rec.state == 'draft' and not rec.x_generated_dgt )
            lock_date = rec.company_id._get_user_fiscal_lock_date()
            if lock_date and rec.invoice_date and rec.invoice_date <= lock_date:
                rec.x_accounting_lock = True
            else:
                rec.x_accounting_lock = False

    @api.depends('restrict_mode_hash_table', 'state', 'x_sequence')
    def _compute_x_show_reset_to_draft_button(self):
        for inv in self:
            inv.x_show_reset_to_draft_button = inv.show_reset_to_draft_button and not inv.x_accounting_lock
            # if self.is_invoice():
            #     inv.x_show_reset_to_draft_button = inv.show_reset_to_draft_button and not(inv.x_sequence or rec.x_state_dgt)
            # else:
            #     inv.x_show_reset_to_draft_button = inv.show_reset_to_draft_button

    @api.depends('state', 'x_sequence')
    def _compute_x_show_generate_xml_button(self):
        for inv in self:
            if inv.is_sale_document():
                # documentos de clientes
                if (inv.state == 'posted' and inv.x_document_type in ('FE','TE','FEE','ND','NC') and not inv.x_sequence):
                    inv.x_show_generate_xml_button = True
                elif inv.state == 'posted' and inv.x_sequence and not inv.x_state_dgt:
                    inv.x_show_generate_xml_button = True
                else:
                    inv.x_show_generate_xml_button = False
            elif inv.is_purchase_document():
                # documentos de proveedores
                if ((inv.state == 'posted' and inv.x_document_type == 'FEC' and not inv.x_sequence)
                        or (inv.x_state_dgt == '1' and not inv.x_xml_comprobante) 
                        or (inv.x_state_dgt == '2')):
                    inv.x_show_generate_xml_button = True
                elif inv.state == 'posted' and inv.x_sequence and not inv.x_state_dgt:
                    inv.x_show_generate_xml_button = True
                else:
                    inv.x_show_generate_xml_button = False                
            else:
                inv.x_show_generate_xml_button = False

    @api.onchange('partner_id', 'company_id')
    def _get_economic_activities(self):
        for inv in self:
            if inv.is_purchase_document():
                # facturación de Proveedores
                if inv.partner_id:
                    inv.x_economic_activity_id = inv.partner_id.x_economic_activity_id
            elif inv.is_sale_document():
                # ventas
                inv.x_economic_activity_id = inv.company_id.x_economic_activity_id

    @api.onchange('partner_id', 'company_id')
    def _onchange_partner_id(self):
        super(FaeAccountInvoice, self)._onchange_partner_id()
        self.x_payment_method_id = self.partner_id.x_payment_method_id or self.x_payment_method_id
        if self.move_type == 'out_refund':
            self.x_document_type = 'NC'
        elif self.partner_id and self.partner_id.x_foreign_partner:
            self.x_document_type = 'FEE'
        elif self.partner_id and self.partner_id.vat:
            if self.partner_id.country_id and self.partner_id.country_id.code != 'CR':
                self.x_document_type = 'TE'
            elif self.partner_id.x_identification_type_id and self.partner_id.x_identification_type_id.code == '05':
                self.x_document_type = 'TE'
            else:
                self.x_document_type = 'FE'
        else:
            self.x_document_type = 'TE'

        if self.is_purchase_document():
            self.x_economic_activity_id = self.partner_id.x_economic_activity_id
        else:            
            self.x_economic_activity_id = self.company_id.x_economic_activity_id


    @api.onchange('partner_id')
    def _partner_changed(self):
        if self.is_purchase_document(include_receipts=True):
            # Son compras a proveedores
            if self.partner_id:
                if self.partner_id.x_payment_method_id:
                    self.x_payment_method_id = self.partner_id.x_payment_method_id
                else:
                    # cuando no se conoce al momento de la emisión se usa Efectivo
                    rec = self.env['xpayment.method'].search([('code', '=', '01')], limit=1) 
                    self.x_payment_method_id = rec.id 
        else:
            # ventas a Clientes
            if (self.partner_id.x_special_tax_type == 'E' 
                and not (self.partner_id.x_exo_type_exoneration and self.partner_id.x_exo_date_issue 
                            and self.partner_id.x_exo_exoneration_number and self.partner_id.x_exo_institution_name) ):
                raise UserError('El cliente es exonerado pero no han ingresado los datos de la exoneración')
            # recalcula lineas (si existen)
            if self.line_ids and self._origin.partner_id != self.partner_id:
                for line in self.line_ids:
                    line._onchange_product_id()
                    line._onchange_price_subtotal()
                self._recompute_dynamic_lines(recompute_all_taxes=True)


    @api.onchange('x_document_type')
    def _document_type_changed(self):
        if not self.x_document_type:
            if not self.x_fae_incoming_doc_id:
                self.x_fae_incoming_doc_id = None
        elif self.move_type == 'out_refund' and self.x_document_type != 'NC':
            self.x_document_type = 'NC'
        elif self.move_type == 'out_invoice' and self.x_document_type not in ('FE','TE','FEE','ND'):
            raise UserError('El tipo de documeto válido es: Factura, Tiquete, Factura Exportación o Nota de débito')
        elif self.x_document_type == 'FEC':
            self.x_fae_incoming_doc_id = None
            partner = self.partner_id
            if partner and not(partner.state_id and partner.x_identification_type_id and partner.vat and partner.email):
                raise UserError('Para Facturas electrónicas de Compra el proveedor debe tener dirección, identificación y correo')
            elif not partner.x_economic_activity_id:
                raise UserError('Para Facturas electrónicas de Compra el proveedor debe tener la actividad económica a la que se dedica')
            rec = self.env['xreference.code'].search([('code','=','04'),('active','=',True)], limit=1) 
            if rec:
                self.x_reference_code_id = rec.id
                self.x_is_external_reference = True
        elif self.x_document_type == 'FEE' and self.partner_id.x_special_tax_type in ('E','R'):
            raise UserError('Lo documentos de Exportación no pueden emitirse a clientes Exonerados')
        elif self.move_type.find('out_') == 0 and self.x_document_type == 'FEC': 
            raise UserError('El tipo de documento "Factura Electrónica de Compra" no es válido en ventas')
        elif self.x_document_type not in ('TE','FEE') and self.partner_id and not self.partner_id.vat:
            raise UserError('Para el tipo de documento electrónico seleccionado, la persona debe tener registrado su número de identificación')

        if not self.x_reference_code_id and self.x_is_external_reference:
            self.x_is_external_reference = False


    @api.onchange('x_fae_incoming_doc_id')
    def _document_incoming_doc(self):
        if self.move_type in ('in_invoice','in_refund'):
            if self.x_document_type == 'FEC':
                self.x_fae_incoming_doc_id = None
            elif self.x_fae_incoming_doc_id:
                if self.x_fae_incoming_doc_id.document_type != self.x_document_type:
                    raise UserError('El tipo de documento recibido (%s) es diferente al indicado en este movimiento (%s)' 
                                    % (self.x_fae_incoming_doc_id.document_type,  self.x_document_type) )
                self.ref = self.x_fae_incoming_doc_id.issuer_sequence or self.ref
                self.load_xml_lines()

 
    @api.onchange('ref','invoice_date')
    def _onchange_reference_info(self):
        if self.x_is_external_reference and self.x_document_type == 'FEC' and not self.x_ext_reference_num:
            rec = self.env['xreference.document'].search([('code', '=', '14')])     # 14 = Comprobante aportado por contribuyente del Régimen de Tributación Simplificado
            self.x_reference_document_type_id = None if not rec else rec.id
            self.x_ext_reference_num = self.ref
            self.x_ext_reference_date = self.invoice_date

    @api.onchange('x_is_external_reference')
    def _onchange_x_is_external_reference(self):        
        if self.x_is_external_reference:
            self.x_invoice_reference_id = None

    @api.onchange('x_invoice_reference_id')
    def _onchange_invoice_reference_id(self):
        if self.x_invoice_reference_id:
            # referencia a un movimiento existente en odoo (in_invoice o out_invoice)
            if self.x_invoice_reference_id.x_document_type in ('FEC','FEE'):
                # 15 = Sustituye una Factura electrónica de Compra
                tipo_doc = '15' if self.x_invoice_reference_id.x_document_type == 'FEC' else '01'
            else:
                tipo_doc = fae_enums.tipo_doc_num.get(self.x_invoice_reference_id.x_document_type)
            if tipo_doc:
                rec = self.env['xreference.document'].search([('code', '=', tipo_doc)]) 
                if rec:
                    self.x_reference_document_type_id = rec.id

    @api.model
    def compute_name_value(self):
        if (not self.x_document_type or (self.is_purchase_document() and not self.x_fae_incoming_doc_id)) and self.name == '/':
            seq_code = None
            values = {}
            if self.move_type == 'out_refund':
                seq_code = 'xfae_number_internal_invoice_rev'
                values['name'] = 'xFAE - Number for Internal Reversal Invoice'
                values['prefix'] = 'RINV-'
            elif 'out_' in self.move_type:
                seq_code = 'xfae_number_internal_invoice'
                values['name'] = 'xFAE - Number for Internal Invoice'
                values['prefix'] = 'INV-'
            elif self.move_tpe == 'in_refund':
                seq_code = 'xfae_number_internal_bill_rev'
                values['name'] = 'xFAE - Number for Internal Reversal Bill'
                values['prefix'] = 'RBILL-'
            elif 'in_' in self.move_type:
                seq_code = 'xfae_number_internal_bill'
                values['name'] = 'xFAE - Number for Internal Bill'
                values['prefix'] = 'BILL-'
            if seq_code:
                sequence = self.env['ir.sequence'].search([('code', '=', seq_code), ('company_id', '=', self.company_id.id)])
                if not sequence:
                    values.update({'company_id': self.company_id.id,
                                    'code': seq_code,
                                    'active': True,
                                    'padding': 6,
                                    'number_next': 1,
                                    'number_increment': 1})
                    sequence = self.env['ir.sequence'].sudo().create(values)
                self.name = sequence.next_by_id()
                numero = self.name


    def action_post(self):
        # _logger.info('>> action_post: entro')
        for inv in self:
            if not inv.is_invoice() or inv.x_state_dgt:
                inv.compute_name_value()
                super(FaeAccountInvoice, inv).action_post()
                continue
            else:
                gen_doc_electronico = False
                if inv.company_id.x_fae_mode in ('api-stag', 'api-prod'):
                    if ((inv.move_type in ('out_invoice','out_refund') and inv.x_document_type)
                            or (inv.move_type == 'in_invoice' and inv.x_document_type == 'FEC')):
                        gen_doc_electronico = True

                if not gen_doc_electronico:
                    if inv.move_type in ('in_invoice','in_refund') and inv.x_fae_incoming_doc_id:
                        inv.x_state_dgt = inv.x_fae_incoming_doc_id.state_response_dgt
                    inv.compute_name_value()
                    super(FaeAccountInvoice, inv).action_post()
                    continue

                else:
                    # Son documentos Electrónicos Emitidos a Cliente o
                    #  una factura electrónica de compra
                    if inv.is_sale_document() and inv.x_document_type:
                        if inv.partner_id and inv.partner_id.vat and not inv.partner_id.x_identification_type_id:
                            raise UserError('Debe indicar el tipo de identificación del cliente')
                        if inv.move_type == 'out_invoice' and not inv.x_payment_method_id:
                            raise UserError('Debe indicar el método de pago')
                        if inv.move_type == 'out_refund' and not inv.x_reference_code_id:
                            raise  UserError('Debe indicar el motivo de referencia ')
                    elif inv.is_purchase_document() and inv.x_document_type:
                        # is_purchase_document() con un documento electrónico seleccionado:
                        if not inv.partner_id:
                            raise UserError('Para documentos electrónicos debe seleccionar un proveedor (contacto)')
                        if inv.partner_id.vat and not inv.partner_id.x_identification_type_id:
                            raise UserError('Debe indicar el tipo de identificación del proveedor')
                        if inv.x_document_type == 'FEC':
                            if not (inv.partner_id.state_id and inv.partner_id.x_country_county_id and inv.partner_id.x_country_district_id):
                                raise UserError('Para Facturas Electrónicas de Compra, debe indicar la Dirección del proveedor (Provincia, Cantón y Distrito)')
                            if not inv.partner_id.email:
                                raise UserError('Para Factura Electrónica de Compra, debe indicar el correo del proveedor')

                    if inv.invoice_payment_term_id and not inv.invoice_payment_term_id.x_sale_condition_id:
                        raise UserError('Debe configurar la condición de venta para el término de pago: %s' % (inv.invoice_payment_term_id.name))

                    if (inv.company_id.x_fae_mode == 'api-stag' and inv.company_id.x_test_expire_date <= datetime.date.today() ):
                        raise UserError('La llave criptográfica de PRUEBAS está vencida, debe actualizarse con una más reciente')
                    elif (inv.company_id.x_fae_mode == 'api-prod' and inv.company_id.x_prod_expire_date <= datetime.date.today() ):
                        raise UserError('La llave criptográfica está vencida, debe actualizarse con una más reciente')

                    # tipo de identificación
                    if not inv.company_id.x_identification_type_id:
                        raise UserError('Debe indicar el tipo de identificación de la compañía')

                    # verifica si existe un tipo de cambio 
                    if inv.currency_id.name != inv.company_id.currency_id.name  and (not inv.currency_id.rate_ids or not (len(inv.currency_id.rate_ids) > 0)):
                        raise UserError(_('No hay tipo de cambio registrado para la moneda %s' % (inv.currency_id.name)))

                    if ((inv.x_reference_code_id or inv.x_reference_document_type_id)
                        and (not inv.x_is_external_reference and not inv.x_invoice_reference_id)):
                        raise UserError('Datos de referencia no están completos')

                    if inv.x_is_external_reference and (not inv.x_ext_reference_num or not inv.x_ext_reference_date):
                        raise UserError('Cuando la referencia es externa a odoo deben llenarse los datos de referencia')

                    if inv.x_document_type:
                        # Revisa las líneas para verificar que los artículos tiene código CAByS
                        for line in inv.invoice_line_ids:
                            if line.display_type:
                                # es una Nota o un Sección
                                continue
                            if not line.product_id:
                                raise UserError('Facturación electrónica no acepta líneas sin código artículo, ver: %s' % line.name)
                            if inv.x_document_type != 'FEE':
                                if not (line.product_id.x_cabys_code_id and line.product_id.x_cabys_code_id.code):
                                    raise UserError('El artículo: %s no tiene código CAByS' % (line.product_id.default_code or line.product_id.name) )
                            elif line.product_id and line.product_id.type != 'service' and not line.product_id.x_tariff_heading:
                                raise UserError('El artículo: %s no tiene partida arancelaria y es requerida en facturas de Exportación'
                                                % (line.product_id.default_code or line.product_id.name) )

                            # es ha sido un error común en los clientes
                            es_servicio = (line.product_id.type == 'service' or line.product_uom_id.category_id.name in ('Services', 'Servicios'))
                            if line.product_uom_id.x_code_dgt == 'Unid' and es_servicio:
                                raise UserError('El artículo: %s es de tipo servicio, pero tiene la unidad: %s '
                                                % ((line.product_id.default_code or line.product_id.name), line.product_uom_id.name) )

                    if not inv.invoice_date:
                        inv.invoice_date = datetime.date.today()

                    if inv.currency_id.name == inv.company_id.currency_id.name:
                        inv.x_currency_rate = 1
                    elif inv.currency_id.rate > 0:
                        inv.x_currency_rate = round(1.0 / inv.currency_id.rate, 2)
                    else:
                        inv.x_currency_rate = None

                    dt_cr = datetime.datetime.today().astimezone(pytz.timezone('America/Costa_Rica'))
                    inv.x_issue_date = dt_cr.strftime('%Y-%m-%dT%H:%M:%S')
                    inv.x_state_dgt = False

                    # Aplica el movimiento en Odoo
                    super(FaeAccountInvoice, inv).action_post()

                    if not (inv.x_electronic_code50 or inv.x_sequence):
                        if inv.move_type == 'out_invoice': # Factura a Cliente
                            if inv.x_document_type == 'FE' and (not inv.partner_id.vat or inv.partner_id.x_identification_type_id.code == 'E'):
                                inv.x_document_type = 'TE'
                        elif inv.move_type == 'out_refund':  # Notas de Crédito
                            inv.x_document_type = 'NC'

                    if inv.x_document_type:
                        self.generate_xml_and_send_dgt(inv)

                    # Si es un doc.de proveedores y corresponde a un doc.recibido entonces asocia este doc con el recibido
                    if inv.is_purchase_document() and inv.x_fae_incoming_doc_id and inv.x_document_type in ('FE','FEE'):
                        inv.x_fae_incoming_doc_id.invoice_id = inv.id
                        inv.x_fae_incoming_doc_id.purchase_registried = True


    # cron Job: Envia a hacienda todos los documentos de clientes no enviados a hacienda
    def _send_invoices_dgt(self, max_invoices=20):  # cron
        # from may-2021 este job se saco de funcionamiento porque por integraciones con otras
        # funcionalidades generaba documentos electrónicos no deseados.
        # se inicia un proceso de desactivacion del cron en clientes que lo tienen funcionando
        pass


    # cron Job: Chequea en hacienda el status de documentos de clientnes enviados
    def _check_status_doc_enviados(self, max_invoices=10):
        out_invoices = self.env['account.move'].search(
                                        [('move_type', 'in', ('out_invoice', 'out_refund', 'in_invoice', 'in_refund')),
                                         ('state', '=', 'posted'),
                                         ('x_state_dgt', '=', 'PRO')], 
                                        limit=max_invoices)
        invoices = out_invoices
        # invoices = out_invoices | in_invoices

        quantity_invoices = len(invoices)
        # _logger.info('>> _check_status_doc_enviados: Cantidad %s', quantity_invoices)
        for inv in invoices:
            # _logger.info('>> _check_status_doc_enviados: %s', inv.x_sequence)
            token_dgt = fae_utiles.get_token_hacienda(inv.company_id, inv.company_id.x_fae_mode)
            state_dgt = fae_utiles.consulta_doc_enviado(inv, token_dgt, inv.company_id.x_fae_mode)
            if inv.is_sale_document() and state_dgt == '1':
                inv.action_send_mail_fae()

    # genera el XML de un documento particular
    def generate_xml_and_send_dgt_manual(self):
        self.ensure_one()
        if self.company_id.x_fae_mode not in ('api-stag', 'api-prod'):
            return
        if self.state != 'draft' and (not self.x_sequence and not self.x_electronic_code50): 
            if not self.invoice_date:
                self.invoice_date = datetime.date.today()
            if not self.x_currency_rate:
                if self.currency_id.name == self.company_id.currency_id.name:
                    self.x_currency_rate = 1
                elif self.currency_id.rate > 0:
                    self.x_currency_rate = round(1.0 / self.currency_id.rate, 5)
        if self.x_document_type:
            self.generate_xml_and_send_dgt(self, write_log=True)


    # genera el XML y envia el documento a la DGT
    def generate_xml_and_send_dgt(self, invoices, write_log=False):
        quantity_invoices = len(invoices)
        count_inv = 0
        for inv in invoices:
            try:
                count_inv += 1
                if write_log:
                    _logger.info('>> generate_xml_and_send:  - fae_mode: %s,  identif_type: %s, move_type: %s,  sequence: %s'
                                , inv.company_id.x_fae_mode, inv.company_id.x_identification_type_id.code, inv.move_type, inv.x_sequence )

                if not inv.company_id.x_fae_mode or inv.company_id.x_fae_mode == 'N':
                    continue

                elif not self.is_invoice():
                    continue

                elif not inv.company_id.x_identification_type_id:
                    inv.message_post(subject='Error',
                                    body='generate_xml_and_send:  Aviso!.\n La compañía no tiene el tipo de identificación')
                    continue

                elif inv.company_id.x_fae_mode == 'api-prod' and not (inv.company_id.x_prod_crypto_key and inv.company_id.x_prod_pin):
                    inv.message_post(subject='Error',
                                    body='generate_xml_and_send:  Aviso!.\n La compañía no tiene configurado parámetros para firmar documentos en PRODUCCION')
                    continue
                elif inv.company_id.x_fae_mode == 'api-stag' and not (inv.company_id.x_test_crypto_key and inv.company_id.x_test_pin):
                    inv.message_post(subject='Error',
                                    body='generate_xml_and_send:  Aviso!.\n La compañía no tiene configurado parámetros para firmar documentos en PRUEBAS')
                    continue


                if write_log:
                    _logger.info('>> generate_xml_and_send:  numero: %s / %s  -  consecutivo: %s', count_inv, quantity_invoices, inv.x_sequence)

                # Si no tiene comprobante o es FE de Compra pero rechazada por hacienda
                if not inv.x_xml_comprobante or (inv.x_document_type == 'FEC' and inv.x_state_dgt == '2'):

                    # previene un error que se dio en un cliente que se genero un Nota de Credito, pero el tipo doc dgt no era NC
                    if inv.move_type == 'out_refund' and inv.x_document_type != 'NC':  # Notas de Crédito
                        inv.x_document_type = 'NC'

                    if not self.x_economic_activity_id:
                        # corrige documento que hayan quedado sin actividad economica
                        if self.is_purchase_document():
                            self.x_economic_activity_id = self.partner_id.x_economic_activity_id
                        else:            
                            self.x_economic_activity_id = self.company_id.x_economic_activity_id

                    if not inv.invoice_date:
                        inv.invoice_date = datetime.date.today()

                    if not inv.x_issue_date:
                        dt_cr = datetime.datetime.today().astimezone(pytz.timezone('America/Costa_Rica'))
                        inv.x_issue_date = dt_cr.strftime('%Y-%m-%dT%H:%M:%S')

                    if not inv.x_currency_rate or inv.x_currency_rate == 0:
                        if inv.currency_id.name == inv.company_id.currency_id.name:
                            inv.x_currency_rate = 1
                        elif inv.currency_id.rate > 0:
                            inv.x_currency_rate = round(1.0 / inv.currency_id.rate, 2)
                        else:
                            inv.x_currency_rate = None

                    # datos de referencia por si los hay
                    numero_documento_referencia = False
                    fecha_emision_referencia = False
                    tipo_documento_referencia = False
                    codigo_referencia = False
                    razon_referencia = False
                    
                    if inv.x_reference_code_id: 
                        if inv.x_is_external_reference:
                            numero_documento_referencia = inv.x_ext_reference_num
                            fecha_emision_referencia = inv.x_ext_reference_date.strftime("%Y-%m-%d") + "T12:00:00-06:00"                            
                        else:
                            numero_documento_referencia = inv.x_invoice_reference_id.x_electronic_code50
                            fecha_emision_referencia = inv.x_invoice_reference_id.x_issue_date
                        tipo_documento_referencia = inv.x_reference_document_type_id.code
                        codigo_referencia = inv.x_reference_code_id.code
                        razon_referencia = inv.x_ext_reference_razon if inv.x_ext_reference_razon else inv.x_reference_code_id.name


                    lines = dict()
                    otros_cargos = dict()
                    num_otros_cargos = 0
                    num_linea = 0
                    total_otros_cargos = 0.0
                    total_servicio_salon = 0.0
                    total_servicio_gravado = 0.0
                    total_servicio_exento = 0.0
                    total_servicio_exonerado = 0.0
                    total_mercaderia_gravado = 0.0
                    total_mercaderia_exento = 0.0
                    total_mercaderia_exonerado = 0.0
                    total_descuento = 0.0
                    total_impuestos = 0.0
                    total_iva_devuelto = 0.00
                    base_subtotal = 0.0
                    _old_rate_exoneration = False

                    if inv.invoice_payment_term_id:
                        sale_condition_code = (inv.invoice_payment_term_id.x_sale_condition_id and inv.invoice_payment_term_id.x_sale_condition_id.code or '01')
                    else:
                        sale_condition_code = '01' 

                    if write_log:
                        _logger.info('>> generate_xml_and_send: Procesa lineas')
                    # procesa las líneas del movimiento
                    for inv_line in inv.invoice_line_ids:
                        
                        if inv_line.display_type in ('line_note','line_section'):
                            continue

                        if inv_line.product_id.x_other_charge_type_id:
                            # Otros Cargos
                            num_otros_cargos += 1
                            otros_cargos[num_otros_cargos] = { 'TipoDocumento': inv_line.product_id.x_other_charge_type_id.code,
                                                                'Detalle': escape(inv_line.name[:150]),
                                                                'MontoCargo': inv_line.price_total
                                                                }
                            if inv_line.x_other_charge_partner_id:
                                otros_cargos[num_otros_cargos]['NombreTercero'] = inv_line.partner_id.name[:100]
                                if inv_line.partner_id.vat:
                                    otros_cargos[num_otros_cargos]['IdentidadTercero'] = inv_line.partner_id.vat

                            total_otros_cargos += inv_line.price_total

                        else:
                            if not inv_line.quantity:
                                continue

                            num_linea += 1

                            # calcula el precio unitario sin el impuesto incluido
                            line_taxes = inv_line.tax_ids.compute_all(inv_line.price_unit, inv.currency_id, 1.0, product=inv_line.product_id, partner=inv.partner_id)

                            price_unit = round(line_taxes['total_excluded'], 5)
                            base_line = round(price_unit * inv_line.quantity, 5)
                            descuento = inv_line.discount and round(price_unit * inv_line.quantity * inv_line.discount / 100.0, 5) or 0.0

                            subtotal_line = round(base_line - descuento, 5)

                            # Elimina la doble comilla en la descripción, por eje. Tabla de 1" x 3" (la doble comilla usada para referirse a pulgada)
                            detalle_linea = inv_line.name[:160].replace('"', '')

                            line = {
                                    "cantidad": inv_line.quantity,
                                    "detalle": escape(detalle_linea),
                                    "precioUnitario": price_unit,
                                    "montoTotal": base_line,
                                    "subtotal": subtotal_line,
                                    "BaseImponible": subtotal_line,
                                    "unidadMedida": inv_line.product_uom_id and inv_line.product_uom_id.x_code_dgt or 'Sp'
                                    }

                            if inv_line.product_id:
                                line["codigo"] = inv_line.product_id.default_code or ''

                                if inv_line.product_id.x_cabys_code_id:
                                    line["codigoCabys"] = inv_line.product_id.x_cabys_code_id.code

                            if inv.x_document_type == 'FEE' and inv_line.product_id and inv_line.product_id.x_tariff_heading:
                                line["partidaArancelaria"] = inv_line.product_id.x_tariff_heading

                            if inv_line.discount and price_unit > 0:
                                total_descuento += descuento
                                line["montoDescuento"] = descuento
                                line["naturalezaDescuento"] = inv_line.x_discount_note or 'Descuento Comercial'

                            # Se generan los impuestos
                            taxes = dict()
                            acum_line_tax = 0.0
                            has_exoneration = False
                            perc_exoneration = 0
                            include_baseImponible = False
                            factor_exoneracion = 0.0   #  relacion respecto al total del IVA, se calcula asi:  porc_exoneracion / porcentaje de IVA 
                            if inv_line.tax_ids:
                                itax = 0
                                taxes_lookup = {}
                                for tx in inv_line.tax_ids:
                                    if inv.partner_id.x_special_tax_type == 'E' and tx.x_has_exoneration:
                                        # Partner Exonerado
                                        has_exoneration = True
                                        perc_exoneration = (tx.x_exoneration_rate or 0)
                                        tax_rate = tx.amount + perc_exoneration
                                        factor_exoneracion = perc_exoneration / tax_rate
                                        taxes_lookup[tx.id] = {'cod_impuesto': tx.x_tax_code_id.code, 
                                                              'tarifa': tax_rate,
                                                              'cod_tarifa_imp': tx.x_tax_rate_id.code,
                                                              'porc_exoneracion': perc_exoneration,  }
                                    else:
                                        tax_rate = tx.amount
                                        taxes_lookup[tx.id] = {'cod_impuesto': tx.x_tax_code_id.code, 
                                                              'tarifa': tax_rate,
                                                              'cod_tarifa_imp': tx.x_tax_rate_id.code,
                                                              'porc_exoneracion': None,  }
                                    # 
                                    if tx.x_tax_rate_id.code == '08' and tax_rate != 13:
                                        inv.message_post(subject='Error',
                                                        body='generate_xml_and_send: Para el artículo: %s, el código de tarifa 08 requiere un porcentaje de impuesto de 13, pero tien: %s' 
                                                            % (inv_line.product_id.default_code, str(tax_rate)) )
                                        raise UserError('Para el artículo: %s, el código de tarifa "08", el porcentaje de interes debe ser 13, pero es: %s', 
                                                        inv_line.product_id.default_code, str(tax_rate) )  

                                    include_baseImponible = (tx.x_tax_code_id.code == '07')

                                for i in line_taxes['taxes']:
                                    # calcula el detalle de impuestos
                                    if taxes_lookup[i['id']]['cod_impuesto'] != '00':  # No 00=Exento
                                        itax += 1
                                        tax_amount = round(subtotal_line * taxes_lookup[i['id']]['tarifa'] / 100, 2)
                                        acum_line_tax += tax_amount
                                        tax = {
                                            'codigo': taxes_lookup[i['id']]['cod_impuesto'],
                                            'tarifa': taxes_lookup[i['id']]['tarifa'],
                                            'monto': tax_amount,
                                            'cod_tarifa_imp': taxes_lookup[i['id']]['cod_tarifa_imp'],
                                        }
                                        # Se genera la exoneración si existe para este impuesto
                                        if has_exoneration:                                            
                                            perc_exoneration = taxes_lookup[i['id']]['porc_exoneracion']
                                            tax_amount_exo = round(subtotal_line * (perc_exoneration / 100), 2)
                                            if tax_amount_exo > tax_amount:
                                                tax_amount_exo = tax_amount

                                            acum_line_tax -= tax_amount_exo  # resta la exoneracion al acumulado de impuesto
                                            tax["exoneracion"] = { "monto_exonera": tax_amount_exo,
                                                                   "porc_exonera": perc_exoneration}

                                        taxes[itax] = tax

                                line["impuesto"] = taxes
                                line["impuestoNeto"] = round(acum_line_tax, 5)

                            if include_baseImponible and inv.x_document_type != 'FEE':
                                line["BaseImponible"] = subtotal_line


                            total_impuestos += acum_line_tax

                            # calcula la distribucion de monto gravados, exonerado y exento
                            if taxes:
                                monto_exento = 0.0
                                if has_exoneration and factor_exoneracion > 0:
                                    monto_exonerado = base_line if factor_exoneracion >= 1 else round(base_line * factor_exoneracion, 5)
                                    monto_gravado = base_line - monto_exonerado
                                else:
                                    monto_gravado = base_line                            
                                    monto_exonerado = 0
                            else:
                                monto_exento = base_line
                                monto_exonerado = 0
                                monto_gravado = 0

                            if write_log:
                                _logger.info('>> generate_xml_and_send:  Line id: %s - ProductId: %s - %s   - type: %s   - templateId: %s '
                                             , str(inv_line.id) , inv_line.product_id.id, inv_line.product_id.name, inv_line.product_id.type
                                             , str(inv_line.product_id.product_tmpl_id.id) )
                            if inv_line.product_id.type == 'service' or inv_line.product_uom_id.category_id.name in ('Services', 'Servicios'): 
                                total_servicio_gravado += monto_gravado
                                total_servicio_exonerado += monto_exonerado
                                total_servicio_exento += monto_exento
                            else:
                                total_mercaderia_gravado += monto_gravado
                                total_mercaderia_exonerado += monto_exonerado
                                total_mercaderia_exento += monto_exento

                            base_subtotal += subtotal_line

                            line["montoTotalLinea"] = round(subtotal_line + acum_line_tax, 5)

                            lines[num_linea] = line

                    total_xml = base_subtotal + total_impuestos + total_otros_cargos - total_iva_devuelto
                    if abs(total_xml - inv.amount_total) > 0.5:
                        # inv.state_tributacion = 'error'
                        inv.message_post(
                            subject='Error',
                            body='Monto factura no concuerda con monto para XML. Factura: %s total XML:%s  base:%s impuestos:%s otros_cargos:%s iva_devuelto:%s' % (
                                  inv.amount_total, total_xml, base_subtotal, total_impuestos, total_otros_cargos, total_iva_devuelto) )
                        continue
                    
                    if write_log:
                        _logger.info('>> generate_xml_and_send: Continua generando el consecutivo')

                    # Genera el consecutivo y clave de 50
                    gen_consecutivo = False
                    sequence = None
                    if inv.x_document_type and (inv.x_document_type == 'FEC' and inv.x_state_dgt == '2'):
                        gen_consecutivo = True
                        inv.message_post(message_type='notification'
                                         ,body='FEC: Factura Electrónica de Compra fue rechazada por Hacienda. Adjuntos los XMLs'
                                         # ,subtype=None
                                         # ,parent_id=False
                                         ,attachments=[[inv.x_xml_comprobante_fname, inv.x_xml_comprobante]
                                                       ,[inv.x_xml_respuesta_fname, inv.x_xml_respuesta] ]
                                         )
                        sequence = inv.company_id.x_sequence_FEC_id
                    elif inv.x_document_type and not (inv.x_electronic_code50 or inv.x_sequence): 
                        gen_consecutivo = True
                        if inv.x_document_type == 'FE':
                            sequence = inv.company_id.x_sequence_FE_id
                        elif inv.x_document_type == 'TE':
                            sequence = inv.company_id.x_sequence_TE_id
                        elif inv.x_document_type == 'FEE':
                            sequence = inv.company_id.x_sequence_FEE_id
                        elif inv.x_document_type == 'NC':
                            sequence = inv.company_id.x_sequence_NC_id
                        elif inv.x_document_type == 'ND':
                            sequence = inv.company_id.x_sequence_ND_id
                        elif inv.x_document_type == 'FEC':
                            sequence = inv.company_id.x_sequence_FEC_id
                        else:
                            raise UserError('El tipo documento: %s no es válido' % (inv.x_document_type) )  

                    if gen_consecutivo:
                        if not sequence:
                            raise UserError('No han definido el consecutivo para el tipo de documento: %s' % (inv.x_document_type) )
                        consecutivo = sequence.next_by_id()
                        jdata = fae_utiles.gen_clave_hacienda(inv, inv.x_document_type, consecutivo, inv.company_id.x_sucursal, inv.company_id.x_terminal)
                        inv.x_electronic_code50 = jdata.get('clave_hacienda')
                        inv.x_sequence = jdata.get('consecutivo')
                        inv.name = inv.x_sequence
                        inv.payment_reference = None

                    #
                    total_servicio_gravado = round(total_servicio_gravado, 5)
                    total_servicio_exento = round(total_servicio_exento, 5)
                    total_servicio_exonerado = round(total_servicio_exonerado, 5)
                    total_mercaderia_gravado = round(total_mercaderia_gravado, 5)
                    total_mercaderia_exento = round(total_mercaderia_exento, 5)
                    total_mercaderia_exonerado = round(total_mercaderia_exonerado, 5)
                    total_otros_cargos = round(total_otros_cargos, 5)
                    total_iva_devuelto = round(total_iva_devuelto, 5)
                    base_subtotal = round(base_subtotal, 5)
                    total_impuestos = round(total_impuestos, 5)
                    total_descuento = round(total_descuento, 5)

                    # crea el XML        
                    if write_log:
                        _logger.info('>> generate_xml_and_send: generando el xml de documento %s', inv.x_sequence)
                    try:
                        xml_str = fae_utiles.gen_xml_v43( inv, sale_condition_code, total_servicio_gravado, total_servicio_exento, total_servicio_exonerado
                                                                ,total_mercaderia_gravado, total_mercaderia_exento, total_mercaderia_exonerado
                                                                ,total_otros_cargos, total_iva_devuelto, base_subtotal, total_impuestos, total_descuento
                                                                ,json.dumps(lines, ensure_ascii=False)
                                                                ,otros_cargos, inv.x_currency_rate, inv.narration
                                                                ,tipo_documento_referencia, numero_documento_referencia
                                                                ,fecha_emision_referencia, codigo_referencia, razon_referencia
                                                                )
                    except Exception as error:
                        raise Exception('Falla ejecutando FAE_UTILES.GEN_XML_V43, error: ' + str(error))


                    # if write_log:
                    #     _logger.info('>> generate_xml_and_send:  Procede a firmar XML de documento %s', inv.x_sequence)

                    if inv.company_id.x_fae_mode == 'api-prod':
                        xml_firmado = fae_utiles.sign_xml(inv.company_id.x_prod_crypto_key, inv.company_id.x_prod_pin, xml_str)
                    else:
                        xml_firmado = fae_utiles.sign_xml(inv.company_id.x_test_crypto_key, inv.company_id.x_test_pin, xml_str)

                    # _logger.info('>> generate_xml_and_send:  XML firmado: %s', xml_firmado)

                    inv.x_xml_comprobante_fname = fae_utiles.get_inv_fname(inv) + '.xml'
                    inv.x_xml_comprobante = base64.encodebytes(xml_firmado)

                else:
                    xml_firmado = inv.x_xml_comprobante
                

                # envia el XML firmado
                if inv.x_state_dgt == '1':
                    response_status = 400
                    response_text = 'ya habia sido enviado y aceptado por la DGT'
                else:
                    if write_log:
                        _logger.info('>> generate_xml_and_send:  Enviad XML %s a la DGT', inv.x_sequence)                    
                    response_json = fae_utiles.send_xml_fe(inv, inv.x_issue_date, xml_firmado, inv.company_id.x_fae_mode)                
                    response_status = response_json.get('status')
                    response_text = response_json.get('text')

                if 200 <= response_status <= 299:
                    inv.x_state_dgt = 'PRO'
                    inv.message_post(subject='Note', body='Documento ' + inv.x_sequence + ' enviado a la DGT')

                    time.sleep(4)   # espera 4 segundos antes de consultar por el status de hacienda
                    inv.sudo().consulta_status_doc_enviado()

                else:
                    if response_text.find('ya fue recibido anteriormente') != -1:
                        inv.x_state_dgt = 'PRO'
                        inv.message_post(subject='Error', body='DGT: Documento recibido anteriormente, queda en espera de respuesta de hacienda')
                    elif inv.x_error_count > 10:
                        inv.message_post(subject='Error', body='DGT: ' + response_text)
                        inv.x_state_dgt = 'ERR'
                        # _logger.error('>> generate_xml_and_send_dgt: Invoice: %s  Status: %s Error sending XML: %s' % (inv.x_electronic_code50, response_status, response_text))
                    else:
                        inv.x_error_count += 1
                        inv.x_state_dgt = 'PRO'
                        inv.message_post(subject='Error', body='DGT: status: %s, text: %s ' % (response_status, response_text) )
                        # _logger.error('>> generate_xml_and_send_dgt: Invoice: %s  Status: %s Error sending XML: %s' % (inv.x_electronic_code50, response_status, response_text))

            except Exception as error:
                inv.message_post( subject='Error',
                                body='generate_xml_and_send_dgt.exception:  Aviso!.\n Error : '+ str(error))
                continue

    def consulta_status_doc_enviado(self):
        if self.company_id.x_fae_mode != 'N':
            for inv in self:
                if inv.x_state_dgt == '1':
                    state_dgt = inv.x_state_dgt
                else:
                    if not inv.x_xml_comprobante_fname:
                        inv.x_xml_comprobante_fname = fae_utiles.get_inv_fname(inv) + '.xml'

                    token_dgt = fae_utiles.get_token_hacienda(inv.company_id, inv.company_id.x_fae_mode)
                    state_dgt = fae_utiles.consulta_doc_enviado(inv, token_dgt, inv.company_id.x_fae_mode)
                if state_dgt == '1' and (not inv.x_state_email or inv.x_state_email != 'E'):
                    inv.action_send_mail_fae()

    def action_invoice_sent(self):
        self.ensure_one()
        # _logger.info('>> action_invoice_sent: entro ** ')
        if self.move_type in ('in_invoice', 'in_refund'):
            # no envia documento a proveedor
            return
        elif self.state == 'draft':
            return

        email_template = self.env.ref('FAE_app.fae_email_template_invoice', raise_if_not_found=False)
        lang = False
        if email_template:
            lang = email_template._render_lang(self.ids)[self.id]
        if not lang:
            lang = get_lang(self.env).code

        email_template.attachment_ids = [(5)]   # delete all attachments ids del template

        if self.partner_id:
            partner_email = (self.partner_id.x_email_fae or self.partner_id.email)
            if partner_email and self.x_state_dgt == '1':
                attachment = self.env['ir.attachment'].search([('res_model','=','account.move'),
                                                                ('res_id','=',self.id),
                                                                ('res_field','=','x_xml_comprobante')], limit=1 )
                if attachment:
                    attachment.name = self.x_xml_comprobante_fname
                    attachment_resp = self.env['ir.attachment'].search( [('res_model', '=', 'account.move'),
                                                                        ('res_id', '=', self.id),
                                                                        ('res_field', '=', 'x_xml_respuesta')], limit=1 )
                    if not attachment_resp:
                        # (6, 0, [IDs]) replace the list of linked IDs (like using (5) then (4,ID) for each ID in the list of IDs)
                        email_template.attachment_ids = [(6, 0, [attachment.id])]
                    else:
                        # solo si se tienen los 2 XMLS se incluyen en el correo
                        attachment_resp.name = self.x_xml_respuesta_fname
                        email_template.attachment_ids = [(6, 0, [attachment.id, attachment_resp.id])]

        compose_form = self.env.ref('account.account_invoice_send_wizard_form', raise_if_not_found=False)

        ctx = dict(
                    default_model='account.move',
                    default_res_id=self.id,
                    default_use_template=bool(email_template),
                    default_template_id=email_template and email_template.id or False,
                    default_composition_mode='comment',
                    mark_invoice_as_sent=True,
                    custom_layout="mail.mail_notification_paynow",
                    model_description=self.with_context(lang=lang).type_name,
                    force_email=True
                    )

        return {
                'name': _('Send Invoice'),
                'type': 'ir.actions.act_window',
                'view_type': 'form',
                'view_mode': 'form',
                'res_model': 'account.invoice.send',                
                'views': [(compose_form.id, 'form')],
                'view_id': compose_form.id,
                'target': 'new',
                'context': ctx,
                }


    # Función para adjuntar los documentos y emviar correo al email del cliente
    def action_send_mail_fae(self):
        self.ensure_one()
        
        if not self.is_sale_document():
            return;
        
        email_template_id = self.env.ref('FAE_app.fae_email_template_invoice', raise_if_not_found=False).id

        if email_template_id and self.partner_id:
            new_state_email = self.x_state_email
            template = self.env['mail.template'].browse(email_template_id)
            partner_email = self.partner_id.email
            if not partner_email:
                new_state_email = 'SC'
            else: 
                attachment = self.env['ir.attachment'].search([('res_model', '=', 'account.move'),
                                                               ('res_id', '=', self.id),
                                                               ('res_field', '=', 'x_xml_comprobante')],
                                                              order='id desc', limit=1)
                if attachment:
                    attachment.name = self.x_xml_comprobante_fname
                    attachment_resp = self.env['ir.attachment'].search([('res_model', '=', 'account.move'),
                                                                        ('res_id', '=', self.id),
                                                                        ('res_field', '=', 'x_xml_respuesta')],
                                                                       order='id desc', limit=1)
                    if attachment_resp:
                        attachment_resp.name = self.x_xml_respuesta_fname
                        template.attachment_ids = [(6, 0, [attachment.id, attachment_resp.id])]

                    template.send_mail(self.id, force_send=True)
                    new_state_email = 'E'
                    self.message_post(subject='Note', body='Documento ' + self.x_sequence + ' enviado al correo: ' + self.partner_id.email )
                else:
                    raise UserError('XML del documento no ha sido generado')

            if not self.x_state_email or(self.x_state_email == 'SC' and new_state_email == 'E'):
                self.x_state_email = new_state_email


    # carga lineas del XML para facturas de Compra
    def load_xml_lines(self):
        return
        # no se ejecuta hasta que este liberado
        if ((not self.x_fae_incoming_doc_id or not self.x_document_type or self.x_document_type != 'FE')
            or not self.company_id.x_load_bill_xml_lines):
            return
        if not self.x_fae_incoming_doc_id.issuer_xml_doc:
            return
        if self.line_ids:
             raise ValidationError("El documento ya tiene líneas digitadas por lo que no se puede cargar las del XML")

        try:
            # doc = minidom.parseString(base64.decodebytes(self.x_fae_incoming_doc_id.issuer_xml_doc))
            doc = etree.fromstring(base64.decodebytes(self.x_fae_incoming_doc_id.issuer_xml_doc))
            ns['nsx'] = doc.nsmap.pop(None)
        except Exception as e:
            raise UserError("Fallo al parsear el XML recibido. Error: %s" % e)
            
        account_id = self.company_id.x_def_expenses_account
    
        # _logger.info('>> action_invoice_sent: xml %s ', str(doc))

        tag_codigoMoneda = doc.xpath("nsx:ResumenFactura/nsx:CodigoTipoMoneda/nsx:CodigoMoneda", namespaces=ns)
        
        currency = 'CRC'
        if tag_codigoMoneda:
            currency = tag_codigoMoneda[0].text
            if not currency:
                currency = 'CRC'
        
        currency_id = self.env['res.currency'].search([('name', '=', currency)], limit=1).id
        if not currency_id:
            raise UserError("No pudo localizar el ID para la moneda: %s" % currency)

        self.currency_id.id = currency_id

        move_lines = self.env['account.move.line']
        num_line = 0
        for line in doc.xpath("nsx:DetalleServicio/nsx:LineaDetalle", namespaces=ns):
            num_line += 1
            uom_id = self.env['uom.uom'].search([('x_code_dgt','=', line.xpath("nsx:UnidadMedida", namespaces=ns)[0].text)], limit=1).id
            
            quantity = (float(line.xpath("nsx:Cantidad", namespaces=ns)[0].text) or 1)
            price_subtotal = float( line.xpath("nsx:SubTotal", namespaces=ns)[0].text)   # antes de impuesto
            price_unit = price_subtotal / quantity
            price_total = float( line.xpath("nsx:MontoTotalLinea", namespaces=ns)[0].text)
            
            total_tax_Net = 0.0
            tag_tax_net = line.xpath("nsx:ImpuestoNeto", namespaces=ns)
            if tag_tax_net:
                total_tax_Net = float(tag_tax_net[0].text)
            taxes = []
            for tax in line.xpath("nsx:Impuesto", namespaces=ns):
                tax_code =  self.env['xtax.code'].search([('code','=',tax.xpath("nsx:Codigo", namespaces=ns)[0].text),
                                                             ('active','=',True),], limit=1)
                tax_rate_code = tax.xpath("nsx:CodigoTarifa", namespaces=ns)[0].text
                tax_rate = float(tax_line.xpath("nsx:Tarifa", namespaces=ns)[0].text)
                tag_exo = tax.xpath("nsx:Exoneracion", namespaces=ns)
                if tag_exo:
                    exo_porc = float(tag_exo.xpath("nsx:PorcentajeExoneracion", namespaces=ns)[0].text)
                    tax_rate = tax_amount - (exo_porc or 0)
                    tax_id = self.env['account.tax'].search([('type_tax_use','=','purchase'),('active','=',True),
                                                          ('tax_code_id','=',tax_code.id),
                                                          ('amount','=',tax_rate),
                                                          ('x_has_exoneration','=',True),
                                                          ('x_exoneration_rate','=',exo_porc)
                                                          ], limit=1).id
                    if not tax_id:
                        raise UserError('No existe un impuesto de código: %s con exoneración del %s and tarifa por aplicar de %s' 
                                        % (tax_code.name, exo_porc, tax_rate))
                else:
                    tax_id = self.env['account.tax'].search([('type_tax_use','=','purchase'),('active','=',True),
                                                          ('tax_code_id','=',tax_code.id),
                                                          ('amount','=',tax_rate),
                                                          ('x_has_exoneration','=',False),
                                                          ], limit=1).id
                    if not tax_id:
                        raise UserError('No existe un impuesto de código: %s tarifa por aplicar de %s' % (tax_code.name, tax_rate))

                taxes.append((4, tax_id))

            _logger.debug('>> load_xml_lines: creando linea de factura')
            new_move_line = self.env['account.move.line'].create({
                'move_id': self.id,
                'name': line.xpath("nsx:Detalle", namespaces=ns)[0].text,
                'price_unit': price_unit,
                'quantity': quantity,
                'uom_id': uom_id,
                'sequence': line.xpath("nsx:NumeroLinea", namespaces=ns)[0].text,
                'account_id': account_id or False,
                'price_subtotal': price_subtotal,
                'price_total': price_total,
            })

            # This must be assigned after line is created
            new_move_line.invoice_line_tax_ids = taxes
            move_lines += new_move_line

            self.line_ids = move_lines
        _logger.info('>> load_xml_lines: xml %s ', str(doc))
        self.x_amount_total = float(doc.xpath("nsx:ResumenFactura/nsx:TotalComprobante", namespaces=ns)[0].text)
        self._recompute_dynamic_lines(recompute_all_taxes=True)
