# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models, _
from ..models import fae_utiles
from odoo.exceptions import Warning,UserError, ValidationError


class XFaeReadLocalDoc(models.TransientModel):
    _name = 'xfae.read_local_doc'
    _description = 'Read local documents'

    xml_doc = fields.Binary(string='Documento XML', attachment=False, copy=False)
    xml_response = fields.Binary(string='Respuesta Hacienda', attachment=False, copy=False)
    pdf = fields.Binary(string='Documento PDF', attachment=False, copy=False)


    def read_document(self):
        self.ensure_one()
        vals_ret = {}
        if self.xml_doc and self.xml_response:
            identification_types = self.env['xidentification.type'].search([])
            company = self.env['res.company'].search([])
            currencies = self.env['res.currency'].search([('name','in',['CRC','USD'])])

            doc_vals = fae_utiles.parser_xml(identification_types, company, currencies, 'manual', self.xml_doc)
            resp_vals = fae_utiles.parser_xml(identification_types, company, currencies, 'manual', self.xml_response)

            clave_hacienda = doc_vals.get('issuer_electronic_code50') 
            if clave_hacienda == resp_vals.get('issuer_electronic_code50'):
                doc_vals.update(resp_vals)
                self.env['xfae.incoming.documents'].save_incoming_document(clave_hacienda, doc_vals, self.pdf)
                vals_ret = { 'type': 'ir.actions.client', 'tag': 'reload', }
            else:
                raise ValidationError('La clave de hacienda del documento no coincide con el de respuesta.')

        return vals_ret
