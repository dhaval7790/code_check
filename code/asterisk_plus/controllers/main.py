# -*- coding: utf-8 -*
# ©️ OdooPBX by Odooist, Odoo Proprietary License v1.0, 2020
import json
import logging
import uuid
from odoo import http, SUPERUSER_ID, registry, release
from odoo.api import Environment
from werkzeug.exceptions import BadRequest, NotFound

logger = logging.getLogger(__name__)

MODULE_NAME = 'asterisk_plus'


def error_response(message):
    response = http.request.make_response(message)
    response.status_code = status=400
    response.headers.set('Content-Type', 'text/plain')
    return response


class AsteriskPlusController(http.Controller):

    def check_ip(self, db=None):
        if db:
            with registry(db).cursor() as cr:
                env = Environment(cr, SUPERUSER_ID, {})
                allowed_ips = env[
                    'asterisk_plus.settings'].sudo().get_param(
                    'permit_ip_addresses')
        else:
            allowed_ips = http.request.env[
                'asterisk_plus.settings'].sudo().get_param(
                'permit_ip_addresses')
        if allowed_ips:
            remote_ip = http.request.httprequest.remote_addr
            if remote_ip not in [
                    k.strip(' ') for k in allowed_ips.split(',')]:
                logger.warning('The IP address %s is not allowed to get caller name!', remote_ip)
                return '{} not allowed'.format(remote_ip)

    def _get_partner_by_number(self, db, number, country_code):
        # If db is passed init env for this db
        dst_partner_info = {'id': None}  # Defaults
        if db:
            try:
                with registry(db).cursor() as cr:
                    env = Environment(cr, SUPERUSER_ID, {})
                    dst_partner_info = env[
                        'res.partner'].sudo().get_partner_by_number(
                        number, country_code)
            except Exception:
                logger.exception('Db init error:')
                return 'Db error, check Odoo logs'
        else:
            dst_partner_info = http.request.env[
                'res.partner'].sudo().get_partner_by_number(
                number, country_code)
        return dst_partner_info

    @http.route('/asterisk_plus/get_caller_name', type='http', auth='none')
    def get_caller_name(self, **kw):
        db = kw.get('db')
        try:
            checked = self.check_ip(db=db)
            if checked is not None:
                return checked
            number = kw.get('number', '').replace(' ', '')  # Strip spaces
            country_code = kw.get('country') or False
            if not number:
                return 'Number not specified'
            dst_partner_info = self._get_partner_by_number(
                db, number, country_code)
            logger.info('get_caller_name number {} country {} id: {}'.format(
                number, country_code, dst_partner_info['id']))
            if dst_partner_info['id']:
                return dst_partner_info['name']
            return ''
        except Exception as e:
            logger.exception('Error:')
            if 'request not bound to a database' in str(e):
                return 'db not specified'
            elif 'database' in str(e) and 'does not exist' in str(e):
                return 'db does not exist'
            else:
                return 'Error'

    @http.route('/asterisk_plus/get_partner_manager', type='http', auth='none')
    def get_partner_manager(self, **kw):
        db = kw.get('db')
        try:
            checked = self.check_ip(db=db)
            if checked is not None:
                return checked
            number = kw.get('number', '').replace(' ', '')  # Strip spaces
            country_code = kw.get('country') or False
            exten = kw.get('exten', False)
            if not number:
                return 'Number not specified in request'
            dst_partner_info = self._get_partner_by_number(
                db, number, country_code)
            if dst_partner_info['id']:
                # Partner found, get manager.
                with registry(db).cursor() as cr:
                    env = Environment(cr, SUPERUSER_ID, {})
                    partner = env['res.partner'].sudo().browse(
                        dst_partner_info['id'])
                    if partner.user_id and partner.user_id.asterisk_users:
                        # We have user configured so let return his exten or channels
                        if exten:
                            result = partner.user_id.asterisk_users[0].exten
                        else:
                            originate_channels = [
                                k.name for k in partner.user_id.asterisk_users[0].channels
                                if k.originate_enabled]
                            result = '&'.join(originate_channels)
                        logger.info(
                            "Partner %s manager search result:  %s",
                            partner.id, result)
                        return result
            return ''
        except Exception as e:
            logger.exception('Error:')
            if 'request not bound to a database' in str(e):
                return 'db not specified'
            elif 'database' in str(e) and 'does not exist' in str(e):
                return 'db does not exist'
            else:
                return 'Error'

    @http.route('/asterisk_plus/get_caller_tags', auth='none', type='http')
    def get_caller_tags(self, **kw):
        db = kw.get('db')
        try:
            checked = self.check_ip(db=db)
            if checked is not None:
                return checked
            number = kw.get('number', '').replace(' ', '')  # Strip spaces
            country_code = kw.get('country') or False
            if not number:
                return 'Number not specified in request'
            dst_partner_info = self._get_partner_by_number(
                db, number, country_code)
            if dst_partner_info['id']:
                # Partner found, get manager.
                partner = http.request.env['res.partner'].sudo().browse(
                    dst_partner_info['id'])
                if partner:
                    return ','.join([k.name for k in partner.category_id])
            return ''
        except Exception as e:
            logger.exception('Error:')
            if 'request not bound to a database' in str(e):
                return 'db not specified'
            elif 'database' in str(e) and 'does not exist' in str(e):
                return 'db does not exist'
            else:
                return 'Error'

    @http.route('/asterisk_plus/ping', type='http', auth='none')
    def asterisk_ping(self, **kwargs):
        dbname = kwargs.get('dbname', 'odoopbx_15')
        with registry(dbname).cursor() as cr:
            env = Environment(cr, SUPERUSER_ID, {})
            try:
                res = env['asterisk_plus.server'].browse(1).local_job(
                    fun='test.ping', sync=True)
                return http.Response('{}'.format(res))
            except Exception as e:
                logger.exception('Error:')
                return '{}'.format(e)

    @http.route('/asterisk_plus/asterisk_ping', type='http', auth='none')
    def ping(self, **kwargs):
        dbname = kwargs.get('dbname', 'demo_15.0')
        with registry(dbname).cursor() as cr:
            env = Environment(cr, http.request.env.ref('base.user_admin').id, {})
            try:
                res = env['asterisk_plus.server'].browse(1).ami_action(
                    {'Action': 'Ping'}, sync=True)
                return http.Response('{}'.format(res))
            except Exception as e:
                logger.exception('Error:')
                return '{}'.format(e)

    @http.route('/asterisk_plus/signup', auth='user')
    def signup(self):
        user = http.request.env['res.users'].browse(http.request.uid)
        email = user.partner_id.email
        if not email:
            return http.request.render('asterisk_plus.email_not_set')
        mail = http.request.env['mail.mail'].create({
            'subject': 'Asterisk calls subscribe request',
            'email_from': email,
            'email_to': 'odooist@gmail.com',
            'body_html': '<p>Email: {}</p>'.format(email),
            'body': 'Email: {}'.format(email),
        })
        mail.send()
        return http.request.render('asterisk_plus.email_sent',
                                   qcontext={'email': email})

    @http.route('/%s/transcript/<int:rec_id>' % MODULE_NAME, methods=['POST'], type='json',
                auth='public', csrf=False)
    def upload_transcript(self, rec_id):
        # Public method protected by the one-time transcription token.
        data = json.loads(http.request.httprequest.get_data(as_text=True))
        rec = http.request.env['%s.recording' % MODULE_NAME].sudo().search([
            ('id', '=', rec_id), ('transcription_token', '!=', False),
            ('transcription_token', '=', data['transcription_token'])
        ])
        if not rec:
            logger.warning('Transcription token %s not found for recording %s',
                data['transcription_token'], rec_id)
            return error_response('Bad taken')
        rec.update_transcript(data)        
        return True


    @http.route('/asterisk_plus/agent', methods=['GET'], type='http',
                auth='public', csrf=False)
    def init_agent(self):
        # Check if Server is already initialized.
        agent_initialized = http.request.env.ref('asterisk_plus.default_server').sudo().agent_initialized
        agent_initialization_open = http.request.env.ref('asterisk_plus.default_server').sudo().agent_initialization_open
        if agent_initialized:
            return error_response('Agent is already initialized.')
        if not agent_initialization_open:
            return error_response('Agent initialization is not open.')
        # Check that registration & subscriptions exist
        is_subscribed = http.request.env['asterisk_plus.settings'].sudo().get_param('is_subscribed')
        is_registered = http.request.env['asterisk_plus.settings'].sudo().get_param('is_registered')
        if not is_registered or not is_subscribed:
            return error_response('Please register and subscribe from the Odoo first!')
        # Get API URL and key and pass to the agent
        data = {
            'api_url': http.request.env['asterisk_plus.settings'].sudo().get_param('api_url'),
            'api_key': http.request.env['asterisk_plus.settings'].sudo().get_param('api_key'),
            'instance_uid': http.request.env['asterisk_plus.settings'].sudo().get_param('instance_uid'),
        }
        http.request.env.ref('asterisk_plus.default_server').sudo().write({
            'agent_initialized': True,
            'agent_initialization_open': False,
        })
        # Set initialized flag to disable future requests.
        logger.info('Agent initialization complete.')
        return http.request.make_response(json.dumps(data))

    @http.route('/asterisk_plus/sip_peers', methods=['GET'], auth='public')
    def get_sip_peers(self):
        """
        Public method protected by the server's security_token
        Generate part of SIP config for Odoo PBX Users
        test:
        curl -v -H "x-security-token: STOKEN" http://ODOO_URL/asterisk_plus/sip_peers
        """
        logger.debug('get_sip_conf: Request for SIP conf')
        # The only params available for change is agent_url and subscription server
        token = http.request.httprequest.headers.get("x-security-token")
        if not token:
            return error_response('; No token!\n')
        server = http.request.env['asterisk_plus.server'].sudo().search(
            [('security_token', '=', token)])
        if not server:
            return error_response('; Bad token!\n')
        if not server.generate_sip_peers:
            return error_response('; Server has generate_sip_peers setting disabled!\n')
        try:
            return server.get_sip_peers()
        except Exception as e:
            logger.exception('Cannot generate SIP peers:')
            return error_response('; Error generating peers, check Odoo log!\n')
