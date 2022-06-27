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
                self.x_life_of_asset = self.method_number - len(data)
                cont = 0
                for lines in data:
                    cont += 1
                    if cont == self.x_life_of_asset:
                        self.x_depreciation = lines.asset_depreciated_value
                    if self.x_depreciation:
                        self.x_actual_value = self.original_value - self.x_depreciation
                    self.x_depreciation_month = data.amount_total
            else:
                self.x_life_of_asset = self.method_number
                self.x_depreciation = 0.0
                self.x_actual_value = self.original_value
                self.x_depreciation_month = asset.depreciation_move_ids[1].amount_total

