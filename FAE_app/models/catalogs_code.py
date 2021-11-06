# -*- coding: utf-8 -*-
from odoo import models, fields, api, _


class xOtherChargeType(models.Model):
    _name = "xother.charge.type"
    _description = 'Tipos documentos otros cargos'

    code = fields.Char(string="Code", size=2, required=True, )
    name = fields.Char(string="Name", size=100, required=True, )
    active = fields.Boolean(string="Active", default=True)


class xReferenceCode(models.Model):
    _name = "xreference.code"
    _description = 'Código de referencia'

    code = fields.Char(string="Code", size=2, required=True, )
    version = fields.Char(string="Version", size=3, required=True, )
    name = fields.Char(string="Name", size=100, required=True, )
    active = fields.Boolean(string="Active", default=True)


class xReferenceDocument(models.Model):
    _name = "xreference.document"
    _description = 'Motivos de referencia a documentos'
    _order = "code"

    code = fields.Char(string="Code", size=2, required=True, )
    name = fields.Char(string="Name", size=100, required=True, )
    used_for = fields.Selection(string="Usado en",
                            selection=[('FEC','Fact.Compra')], )
    active = fields.Boolean(string="Active", default=True)


class xTaxUseCode(models.Model):
    _name = "xtax.use.code"
    _description = 'Código de utilización del impuesto pagado en compras'

    code = fields.Char(string="Code", size=2, required=True, )
    name = fields.Char(string="Name", size=100, required=True, )
    description = fields.Char(string="Name", required=True, )
    active = fields.Boolean(string="Active", default=True)