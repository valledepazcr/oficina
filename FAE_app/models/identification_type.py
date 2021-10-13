# -*- coding: utf-8 -*-

from odoo import models, fields, api, _


class xIdentificationType(models.Model):
    _name = "xidentification.type"
    _description = 'Identification type'

    code = fields.Char(string="Código", required=False, size=2)
    name = fields.Char(string="Nombre", required=False, size=20)
    type = fields.Selection([('F', 'Persona Física'),
                             ('J', 'Persona Jurídica')], string='Type')