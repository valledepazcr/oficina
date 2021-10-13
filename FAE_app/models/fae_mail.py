# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
import poplib
from imaplib import IMAP4, IMAP4_SSL
from poplib import POP3, POP3_SSL
from odoo import api, fields, models, tools, _
from odoo.exceptions import UserError


_logger = logging.getLogger(__name__)
MAX_POP_MESSAGES = 50
MAIL_TIMEOUT = 60
XML_DOC_TYPE = {'01': 'FE', '02': 'ND', '03': 'NC', '04': 'TE', '09': 'FEE'}
poplib._MAXLINE = 65536


class FaeMail(models.Model):
    """FAE POP/IMAP mail server account"""

    _name = 'xfae.mail'
    _description = 'FAE Mail Server'
    _order = 'priority'

    name = fields.Char('Nombre', required=True)
    active = fields.Boolean('Activo', default=True)
    state = fields.Selection([
        ('draft', 'No Confirmado'),
        ('done', 'Confirmado'),
    ], string='Status', index=True, readonly=True, copy=False, default='draft')
    server = fields.Char(string='Nombre de Servidor', readonly=True, help="Hostname or IP of the mail server", states={'draft': [('readonly', False)]})
    port = fields.Integer(string='Puerto', readonly=True, states={'draft': [('readonly', False)]})
    server_type = fields.Selection([
        ('pop', 'Servidor POP'),
        ('imap', 'Servidor IMAP'),
    ], string='Tipo de Servidor', index=True, required=True, default='imap')
    smtp_encryption = fields.Selection([('none', 'None'),
                                        ('starttls', 'TLS (STARTTLS)'),
                                        ('ssl', 'SSL/TLS')],
                                       string='Seguridad de conexión', required=True, default='none',
                                       help="Choose the connection encryption scheme:\n"
                                            "- None: SMTP sessions are done in cleartext.\n"
                                            "- TLS (STARTTLS): TLS encryption is requested at start of SMTP session (Recommended)\n"
                                            "- SSL/TLS: SMTP sessions are encrypted with SSL/TLS through a dedicated port (default: 465)")

    is_ssl = fields.Boolean('SSL/TLS', help="Connections are encrypted with SSL/TLS through a dedicated port (default: IMAPS=993, POP3S=995)")
    date = fields.Datetime(string='Última fecha de conexión', readonly=True)
    user = fields.Char(string='Usuario', readonly=True, states={'draft': [('readonly', False)]})
    password = fields.Char(string='Contraseña', readonly=True, states={'draft': [('readonly', False)]})
    priority = fields.Integer(string='Prioridad', readonly=True, states={'draft': [('readonly', False)]}, help="Defines the order of processing, lower values mean higher priority", default=5)
    type = fields.Selection([('in', 'Servidor de Correo Entrante'),('out', 'Servidor de Correo Saliente'),
                             ], string='Tipo', default='in')
    next_email = fields.Many2one('xfae.mail', string="Siguiente Correo")
    max_num_mail = fields.Integer(string='Límite diario')

    @api.onchange('server_type', 'is_ssl')
    def onchange_server_type(self):
        self.port = 0
        if self.server_type == 'pop':
            self.port = self.is_ssl and 995 or 110
        elif self.server_type == 'imap':
            self.port = self.is_ssl and 993 or 143
        else:
            self.server = ''

    @api.onchange('type')
    def onchange_type(self):
        self.port = 0
        if self.type == 'in' and self.server_type == 'pop':
            self.port = self.is_ssl and 995 or 110
        elif self.type == 'in' and self.server_type == 'imap':
            self.port = self.is_ssl and 993 or 143
        elif self.type == 'out':
            self.port = 25

    @api.model
    def create(self, values):
        res = super(FaeMail, self).create(values)
        return res

    def write(self, values):
        res = super(FaeMail, self).write(values)
        return res

    def unlink(self):
        res = super(FaeMail, self).unlink()
        return res

    def set_draft(self):
        self.write({'state': 'draft'})
        return True

    def connect(self):
        self.ensure_one()
        if self.server_type == 'imap':
            if self.is_ssl:
                connection = IMAP4_SSL(self.server, int(self.port))
            else:
                connection = IMAP4(self.server, int(self.port))
            connection.login(self.user, self.password)
        elif self.server_type == 'pop':
            if self.is_ssl:
                connection = POP3_SSL(self.server, int(self.port))
            else:
                connection = POP3(self.server, int(self.port))
            #TODO: use this to remove only unread messages
            #connection.user("recent:"+server.user)
            connection.user(self.user)
            connection.pass_(self.password)
        # Add timeout on socket
        connection.sock.settimeout(MAIL_TIMEOUT)

        return connection

    def button_confirm_login(self):
        for server in self:
            if self.type == 'in':
                try:
                    connection = server.connect()
                    server.write({'state': 'done'})
                except Exception as err:
                    _logger.info("Failed to connect to %s server %s.", server.server_type, server.name, exc_info=True)
                    raise UserError(_("Connection test failed: %s") % tools.ustr(err))
                finally:
                    try:
                        if connection:
                            if server.server_type == 'imap':
                                connection.close()
                            elif server.server_type == 'pop':
                                connection.quit()
                    except Exception:
                        # ignored, just a consequence of the previous exception
                        pass
        return True
