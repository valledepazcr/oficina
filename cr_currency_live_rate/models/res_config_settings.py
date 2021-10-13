from odoo import models, fields, api, _


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    x_exchange_source = fields.Selection(string="Origen del tipo de cambio", 
                                        selection=[('disabled', 'Deshabilitado'), 
                                                    ('bccr', 'Banco Central (BCCR)'), 
                                                    ('hacienda', 'Hacienda')], 
                                        required=True, default='disabled')
    x_bccr_username = fields.Char(string="Usuario registrado en BCCR" )
    x_bccr_email = fields.Char(string="e-mail registrado en BCCR" )
    x_bccr_token = fields.Char(string="Token de conexión" )


    @api.model
    def get_values(self):
        res = super(ResConfigSettings, self).get_values()
        get_param = self.env['ir.config_parameter'].sudo().get_param
        res.update(
            x_bccr_username=get_param('x_bccr_username'),
            x_bccr_email=get_param('x_bccr_email'),
            x_bccr_token=get_param('x_bccr_token'),
            x_exchange_source=get_param('x_exchange_source'),            
        )
        return res

    def set_values(self):
        super(ResConfigSettings, self).set_values()
        set_param = self.env['ir.config_parameter'].sudo().set_param
        set_param('x_bccr_username', self.x_bccr_username)
        set_param('x_bccr_email', self.x_bccr_email)
        set_param('x_bccr_token', self.x_bccr_token)
        set_param('x_exchange_source', self.x_exchange_source)        
