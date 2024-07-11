import json
import logging
from odoo import models, fields, api, tools, release, _
from odoo.exceptions import ValidationError, UserError
from .server import get_default_server
from .settings import debug

logger = logging.getLogger(__name__)


class ResUser(models.Model):
    _inherit = 'res.users'

    asterisk_users = fields.One2many(
        'asterisk_plus.user', inverse_name='user')    
    # Server of Agent account, One2one simulation.
    asterisk_server = fields.Many2one('asterisk_plus.server', compute='_get_asterisk_server')

    @api.model
    def create(self, values):
        user = super().create(values)
        debug(self, "Created user {}".format(user.login))
        # create SIP account if enabled and not when installing.
        if not self.env.context.get('install_mode'):
            server = self.env.ref('asterisk_plus.default_server')
            if server.auto_create_pbx_users:
                self.env['asterisk_plus.user'].auto_create(user)
        return user

    def _get_asterisk_server(self):
        for rec in self:
            # There is an unique constraint to limit 1 user per server.
            rec.asterisk_server = self.env['asterisk_plus.server'].search(
                [('user', '=', rec.id)], limit=1)

    def get_pbx_user_settings(self):
        return True
