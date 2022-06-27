# -*- coding: utf-8 -*-

from odoo import models, fields, api


class accountAsset(models.Model):
    _inherit = 'account.asset'

    x_life_of_asset = fields.Integer('Vida util(meses)', compute='_set_data_asset')
    x_depreciation = fields.Float('Depreciación acumulada', compute='_set_data_asset')
    x_actual_value = fields.Float('Valor actual', compute='_set_data_asset')
    x_depreciation_month = fields.Float('Depreciación por mes', compute='_set_data_asset')

    def _set_data_asset(self):
        for asset in self:
            data = asset.depreciation_move_ids.filtered(lambda c: c.state == 'posted')
            if data:
                asset.x_life_of_asset = asset.method_number - len(data)
                cont = 0
                for lines in data:
                    cont += 1
                    if cont == asset.x_life_of_asset:
                        asset.x_depreciation = lines.asset_depreciated_value
                    if asset.x_depreciation:
                        asset.x_actual_value = asset.original_value - asset.x_depreciation
                    asset.x_depreciation_month = data.amount_total
            else:
                asset.x_life_of_asset = asset.method_number
                asset.x_depreciation = 0.0
                asset.x_actual_value = asset.original_value
                asset.x_depreciation_month = asset.depreciation_move_ids[1].amount_total

