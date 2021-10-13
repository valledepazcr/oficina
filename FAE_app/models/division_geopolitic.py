# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError


class ResCountryCounty(models.Model):
    _name = "xcountry.county"
    _description = 'County per country state'
    _order = 'code'

    country_state_id = fields.Many2one("res.country.state", string="Province", required=True)
    code = fields.Char(string="Code", required=True, size=3)
    name = fields.Char(string="County", required=True, size=40)


class ResCountryDistrict(models.Model):
    _name = "xcountry.district"
    _description = 'District per county'
    _order = 'code'

    country_state_id = fields.Many2one("res.country.state", string="Province", required=True)
    country_county_id = fields.Many2one("xcountry.county", string="County", required=True, domain="[('country_state_id', '=', country_state_id)]")
    code = fields.Char(string="Code", required=True, size=5)
    name = fields.Char(string="District", required=True, size=40)
