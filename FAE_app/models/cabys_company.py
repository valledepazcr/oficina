# -*- coding: utf-8 -*-
from odoo import models, fields, api, _

from odoo.exceptions import Warning, UserError, ValidationError


class xCabysCompany(models.Model):
    _name = "xcabys.company"
    _description = 'CAByS SubSet'
    _order = 'company_id, code'

    code = fields.Char(string="Code", required=True, )
    name = fields.Char(string="Name", required=True, 
                        help='Nombre corto para desplegar en el campo de la vista.'
                             'Por default puede ser el código más una descripción breve')  # nombre abreviado para desplegar en el campo de la vista
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)
    description = fields.Char(string="Description", 
                        help='Descripción que tiene el catalogo de hacienda')  # descripción que tiene Hacienda en el catalogo    
    impuesto = fields.Char(string="Desc.Tax", size=15, )
    active = fields.Boolean(string="Active", default=True)


    @api.onchange('code')
    def _onchange_code(self):
        if self.code: 
            if len(self.code) != 13:
                raise ValidationError('El código CAByS debe tener una longitud de 13 dígitos')

    @api.onchange('description')
    def _onchange_description(self):
        if self.description and not self.name:
            descripcion = (self.description or " ")
            self.name = self.code + ' - ' + descripcion[:120]
