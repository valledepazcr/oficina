# -*- coding: utf-8 -*-
from odoo import models, fields, api, _


class xExoAuthorization(models.Model):
    _name = "xexo.authorization"
    _description = 'Exoneration Authorization'

    code = fields.Char(string="Code", size=2, )
    name = fields.Char(string="Name", size=160, )
    active = fields.Boolean(string="Active", default=True)

