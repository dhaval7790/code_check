import logging
from odoo import models, fields, api, tools, release, _
from odoo.exceptions import ValidationError, UserError
from passlib import pwd
from random import choice
from .server import get_default_server
from .settings import debug

logger = logging.getLogger(__name__)


class PbxUser(models.Model):
    _name = 'asterisk_plus.user'
    _inherit = 'mail.thread'
    _description = 'Asterisk User'

    exten = fields.Char()
    user = fields.Many2one('res.users', required=True,
                           ondelete='cascade',
                           # Exclude shared users
                           domain=[('share', '=', False)])
    name = fields.Char(related='user.name', readonly=True)
    #: Server where the channel is defined.
    server = fields.Many2one('asterisk_plus.server', required=True,
                             ondelete='restrict', default=get_default_server)
    generate_sip_peers = fields.Boolean(related='server.generate_sip_peers')
    channels = fields.One2many('asterisk_plus.user_channel',
                               inverse_name='asterisk_user')
    originate_vars = fields.Text(string='Channel Variables')
    open_reference = fields.Boolean(
        default=True,
        help=_('Open reference form on incoming calls.'))
    user_call_count = fields.Integer(compute='_get_call_count', string='Calls')
    missed_calls_notify = fields.Boolean(
        default=True,
        help=_('Notify user on missed calls.'))
    call_popup_is_enabled = fields.Boolean(
        default=True,
        string='Call Popup')
    call_popup_is_sticky = fields.Boolean(
        default=False,
        string='Popup Is Sticky')

    _sql_constraints = [
        ('exten_uniq', 'unique (exten,server)',
         _('This phone extension is already used!')),
        ('user_uniq', 'unique ("user",server)',
         _('This user is already defined!')),
    ]

    @api.model
    def create(self, vals):
        user = super(PbxUser, self).create(vals)
        if user and not self.env.context.get('no_clear_cache'):
            self.pool.clear_caches()
        return user

    def write(self, vals):
        user = super(PbxUser, self).write(vals)
        if user and not self.env.context.get('no_clear_cache'):
            self.pool.clear_caches()
        return user

    @api.model
    def has_asterisk_plus_group(self):
        """Used from actions.js to check if Odoo user is enabled to
        use Asterisk applications in order to start a bus listener.
        """
        if (self.env.user.has_group('asterisk_plus.group_asterisk_admin') or
                self.env.user.has_group(
                    'asterisk_plus.group_asterisk_user')):
            return True

    def _get_originate_vars(self):
        self.ensure_one()
        res = set(['__REALCALLERIDNUM={}'.format(self.exten)])
        try:
            if self.originate_vars:
                res.update([k for k in self.originate_vars.split('\n') if k])
        except Exception:
            logger.exception('Get originate vars error:')
        return list(res)

    def dial_user(self):
        self.ensure_one()
        self.env.user.asterisk_users[0].server.originate_call(
            self.exten, model='asterisk_plus.user', res_id=self.id)

    def open_user_form(self):
        if self.env.user.has_group('asterisk_plus.group_asterisk_admin'):
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'asterisk_plus.user',
                'name': 'Users',
                'view_mode': 'tree,form',
                'view_type': 'form',
                'target': 'current',
            }
        else:
            if not self.env.user.asterisk_users:
                raise ValidationError('PBX user is not configured!')
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'asterisk_plus.user',
                'res_id': self.env.user.asterisk_users.id,
                'name': 'User',
                'view_id': self.env.ref(
                    'asterisk_plus.asterisk_plus_user_user_form').id,
                'view_mode': 'form',
                'view_type': 'form',
                'target': 'current',
            }

    @api.model
    def auto_create(self, users):
        """Auto create pbx user for every record in "users" recordset
        """
        extensions = {int(el) for el in self.search([]).mapped('exten') if el.isdigit()}
        if extensions:
            next_extension = max(extensions) + 1
        else:
            try:
                next_extension = int(self.env.ref('asterisk_plus.default_server').sip_peer_start_exten)
            except Exception as e:
                logger.exception('Wrong value for starting extension, taking 101.')
                next_extension = 101

        for user in users:
            # create SIP account only for internal users
            if not user.has_group('base.group_user'):
                continue

            # Add user to the group.
            pbx_group = self.env.ref('asterisk_plus.group_asterisk_user')
            pbx_group.users = [(4, user.id)]

            # create new pbx user
            debug(self, "Creating pbx user {} with extension {}".format(user.login, next_extension))
            asterisk_user = self.create([
                {'exten': "{}".format(next_extension), 'user': user.id},
            ])

            # Generate sip_user from user.login (without @domain) + user id
            sip_user = next_extension
            server = self.env.ref('asterisk_plus.default_server')
            # create new channel for newly created user
            user_channel = self.env['asterisk_plus.user_channel'].create({
                'name': '{}/{}'.format(server.sip_protocol, sip_user),
                'server': server.id,
                'asterisk_user': asterisk_user.id,
                'sip_user': sip_user,
                'sip_password': pwd.genword(length=choice(range(12,16))),
            })
            debug(self, 'Create sip_user {} id {} for {}'.format(user_channel.sip_user, user_channel.id, user.login))
            next_extension += 1


    def _get_call_count(self):
        for rec in self:
            rec.user_call_count = self.env[
                'asterisk_plus.call'].sudo().search_count(
                ['|', ('calling_user', '=', rec.user.id),
                      ('answered_user', '=', rec.user.id)])

    def action_view_calls(self):
        # Used from the user calls view button.
        self.ensure_one()
        return {
            'name': _("Calls"),
            'type': 'ir.actions.act_window',
            'view_mode': 'tree',
            'res_model': 'asterisk_plus.call',
            'domain': ['|', ('calling_user', '=', self.user.id),
                            ('answered_user', '=', self.user.id)],
        }
