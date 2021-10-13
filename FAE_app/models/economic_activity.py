# -*- coding: utf-8 -*-
from odoo import models, fields, api, _


class xEconomicActivity(models.Model):
    _name = "xeconomic.activity"
    _description = 'Economic Activity'

    # Por default las actividades son activadas cuando en  compañías se consultan las actividades en hacienda
    code = fields.Char(string="Code", size=6)
    name = fields.Char(string="Name", size=160)
    active = fields.Boolean(string="Active", default=False)
