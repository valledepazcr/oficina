# -*- coding: utf-8 -*-
# from odoo import http


# class VallesPazUpdate(http.Controller):
#     @http.route('/valles_paz_update/valles_paz_update/', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/valles_paz_update/valles_paz_update/objects/', auth='public')
#     def list(self, **kw):
#         return http.request.render('valles_paz_update.listing', {
#             'root': '/valles_paz_update/valles_paz_update',
#             'objects': http.request.env['valles_paz_update.valles_paz_update'].search([]),
#         })

#     @http.route('/valles_paz_update/valles_paz_update/objects/<model("valles_paz_update.valles_paz_update"):obj>/', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('valles_paz_update.object', {
#             'object': obj
#         })
