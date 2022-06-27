# -*- coding: utf-8 -*-
{
    'name': "valle de paz update",

    'summary': """
        Modulo que se encarga de las modificasiones personalizadas de valle de paz
    """,

    'description': """
        -Modificasion de la vista del tree de activos
    """,

    'author': "PROINTEC",
    'website': "http://www.prointeccr.com",
    'category': 'Uncategorized',
    'version': '0.1',

    'depends': ['base', 'account', 'account_asset'],

    # always loaded
    'data': [
        'views/account_asset_views.xml',
    ],
}
