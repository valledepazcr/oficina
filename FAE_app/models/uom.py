# -*- coding: utf-8 -*-
from odoo import models, fields, api, _


class UoM(models.Model):
    _inherit = "uom.uom"

    x_code_dgt = fields.Char(string="Code DGT", size=15, required=False, )

