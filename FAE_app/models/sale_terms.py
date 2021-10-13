# -*- coding: utf-8 -*-
from odoo import models, fields, api, _


class xSaleCondition(models.Model):
    _name = "xsale.condition"
    _description = 'Sale condition'

    code = fields.Char(string="Code", size=2, required=True, )
    name = fields.Char(string="Name", size=100, required=True, )
    active = fields.Boolean(string="Active", required=True, default=True)


class xPaymentMethod(models.Model):
    _name = "xpayment.method"
    _description = 'Payment method'

    code = fields.Char(string="Code", size=2, required=True, )
    name = fields.Char(string="Name", size=100, required=True, )
    active = fields.Boolean(string="Active", required=True, default=True)


class AccountPaymentTerm(models.Model):
    _inherit = "account.payment.term"

    x_sale_condition_id = fields.Many2one("xsale.condition", string="Condiciones de venta")
