# -*- coding: utf-8 -*-
{
    'name': "Currency Exchange Rate live for Costa Rica",
    'summary':
        """
        Get the currency exchange rate from Banco Central de Costa Rica
        """,
    'version': '14.0',
    'category': 'Extra Tools',
    'author': "PROINTEC",    
    'website': "http://www.prointeccr.com",
    'license': 'AGPL-3',
    'depends': ['base', 'account', ],
    'data': [
        'data/decimal_precision_data.xml',
        'views/res_config_settings_views.xml',
        'views/res_currency_rate_view.xml',
        'cron_task/cron_currency_rate.xml',

    ],
    'external_dependencies': {'python': ['zeep']},
    'application': False,    
    'installable': True,
    'auto_install': False,
}
