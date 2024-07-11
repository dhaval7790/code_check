# -*- coding: utf-8 -*-
# ©️ OdooPBX by Odooist, Odoo Proprietary License v1.0, 2023
import base64
from datetime import datetime
import json
import logging
import re
import requests
import time
import urllib
import urllib3
import sys
if sys.version_info[0] > 2:
    from urllib.parse import urljoin
else:
    from urlparse import urljoin
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
import uuid
from pynats import NATSClient
from odoo import api, models, fields, SUPERUSER_ID, registry, release, tools, _
from odoo.exceptions import ValidationError, UserError
from .settings import debug
from .res_partner import strip_number, format_number



logger = logging.getLogger(__name__)

DEFAULT_SIP_TEMPLATE="""[{username}](odoo-user)
inbound_auth/username = {username}
inbound_auth/password = {password}
endpoint/callerid = {callerid}
hint_exten = {exten}
"""

def get_default_server(rec):
    try:
        return rec.env.ref('asterisk_plus.default_server')
    except Exception:
        logger.exception('Cannot get default server!')
        return False


class Server(models.Model):
    _name = 'asterisk_plus.server'
    _description = "Asterisk Server"

    name = fields.Char(required=True)
    subscription_status = fields.Selection([('new', 'Not Active'),('active','Active')],
        compute='_get_subscription_status')
    is_module_update = fields.Boolean()
    market_download_link = fields.Html(compute='_get_market_download_link')
    is_check_new_enabled = fields.Boolean(default=True)
    user = fields.Many2one('res.users', ondelete='restrict', required=True, readonly=True)
    tz = fields.Selection(related='user.tz', readonly=False)
    country_id = fields.Many2one(related='user.country_id', readonly=False)
    agent_initialized = fields.Boolean()
    agent_initialization_open = fields.Boolean(default=True)
    auto_create_pbx_users = fields.Boolean(string="Autocreate PBX Users",
        help="Automatically generate PBX users for Odoo users")
    generate_sip_peers = fields.Boolean(string='Generate SIP peers',
        help="""Enable get_sip_conf controller.
        It generates part of Asterisk SIP config file according to SIP Conf Template
        for each channel of every PBX User
        It can be included in sip.conf or pjsip_wizard.conf with line:
        #tryexec curl -H "x-security-token: TOKEN" ODOO_URL/asterisk_plus/sip_peers""")
    sip_peer_template = fields.Text(
        string="SIP Peer Template",
        help="SIP configuration template for PBX users",
        default=DEFAULT_SIP_TEMPLATE)
    security_token = fields.Char(required=False, default=lambda x: uuid.uuid4())
    sip_protocol = fields.Selection(string='SIP protocol',
        selection=[('SIP', 'SIP'), ('PJSIP', 'PJSIP')], default='PJSIP', required=True)
    sip_peer_start_exten = fields.Char('Starting Exten', default='101')

    _sql_constraints = [
        ('user_unique', 'UNIQUE("user")', 'This user is already used for another server!'),
    ]

    def write(self, vals):
        autocreate_enabled =  vals.get('auto_create_pbx_users', False)
        if autocreate_enabled:
            self.run_auto_create_pbx_users()
        return super().write(vals)

    @api.model
    def run_auto_create_pbx_users(self):
        debug(self, 'Run autocreate PBX users')
        users = self.env['res.users'].search([])
        pbx_users = self.env['asterisk_plus.user'].search([]).mapped('user')
        self.env['asterisk_plus.user'].auto_create(users-pbx_users)

    def get_sip_peers(self):
        if not self.generate_sip_peers:
            logger.info('SIP peers generation is not enabled.')
            return
        sip_content = ";AUTOGENERATED BY ASTERISK PLUS\n\n"
        for channel in self.env['asterisk_plus.user_channel'].sudo().search(
                [('server', '=', self.id)]):
            if not channel.sip_password:
                logger.info('SIP channel %s has not password, not including.', channel.name)
                continue
            sip_content += self.sip_peer_template.format(
                password=channel.sip_password,
                username=channel.sip_user,
                exten=channel.asterisk_user.exten,
                callerid='{} <{}>'.format(channel.user.name, channel.asterisk_user.exten)
            )
            sip_content += '\n\n'
        return sip_content


    def _get_subscription_status(self):
        for rec in self:
            rec.subscription_status = 'active' if self.env['asterisk_plus.settings'].get_param(
                'is_subscribed') == True else 'new'

    def _get_market_download_link(self):
        for rec in self:
            rec.market_download_link = '<a href="https://apps.odoo.com/apps/{}/asterisk_plus" target="_blank">Download new version of Asterisk Plus app.</a>'.format(
                tools.odoo.release.major_version)    

    def open_server_form(self):
        rec = self.env.ref('asterisk_plus.default_server')
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'asterisk_plus.server',
            'res_id': rec.id,
            'name': 'Agent',
            'view_mode': 'form',
            'view_type': 'form',
            'target': 'current',
        }

    def local_job(self, fun, args=None, kwargs=None, timeout=6,
                  res_model=None, res_method=None, res_notify_uid=None,
                  res_notify_title='PBX', pass_back=None, 
                  raise_exc=True):
        self.ensure_one()
<<<<<<< HEAD
        if self.connection_mode == 'cloud':
            return self.cloud_rpc(fun, arg=arg, kwarg=kwarg, timeout=timeout,
                res_model=res_model, res_method=res_method, res_notify_uid=res_notify_uid,
                pass_back=pass_back, sync=sync, raise_exc=raise_exc)
        if self.connection_mode == 'nats':
            return self.nats_rpc(fun, arg=arg, kwarg=kwarg, timeout=timeout,
                res_model=res_model, res_method=res_method, res_notify_uid=res_notify_uid,
                pass_back=pass_back, sync=sync, raise_exc=raise_exc)
        else:
            raise Exception('Connection not supported.')

    def nats_rpc(self, fun, arg=None, kwarg=None, timeout=5,
                  res_model=None, res_method=None, res_notify_uid=None,
                  pass_back=None, sync=False, raise_exc=True):
        service, method = fun.split('.')
        data=json.dumps({
            'service': service, 'method': method, 'args': arg, 'kwargs': kwarg,
            'timeout': 'timeout', 'res_model': res_model, 'res_method': res_method,
            'res_notify_uid': res_notify_uid, 'pass_back': pass_back, 'sync': sync,
            }).encode('utf-8')
        try:
            with NATSClient(self.nats_url, socket_timeout=timeout) as client:
                client.connect()
                if sync:
                    res = client.request(subject=fun, payload=data)
                    return json.loads(res.payload.decode('utf-8'))
                else:
                    client.publish(subject=fun, payload=data)
        except Exception as e:
            if raise_exc:
                raise
            else:
                logger.exception('NATs error:')    

    @api.model
    def set_agent_data(self, data):
        serv = self.env.user.asterisk_server
        serv.write(data)
        logger.info('Asterisk Plus Agent connected.')
        return True


    def ping_agent(self):
        """Called from server form to test the connectivity.

        Returns:
            True or False if Salt minion is not connected.
        """
        from .server import get_default_server
        server = get_default_server(self)
        res = server.local_job(fun='test.ping', res_notify_uid=self.env.user.id,
            sync=True, timeout=5)
        if res:
            self.env.user.asterisk_plus_notify('Sync reply', title='Test')
=======
        res = {}
        response = None
        try:
            if not self.env['asterisk_plus.settings'].get_param('is_subscribed'):
                raise ValidationError('Subscription is not valid!')
            api_key = self.env['ir.config_parameter'].sudo().get_param(
                'odoopbx.api_key')
            api_url = self.env['ir.config_parameter'].sudo().get_param(
                'odoopbx.api_url')
            instance_uid = self.env['ir.config_parameter'].sudo().get_param(
                'database.uuid')
            data = {
                'fun': fun, 'args': args, 'kwargs': kwargs,
                'res_model': res_model, 'res_method': res_method,
                'res_notify_uid': res_notify_uid,
                'res_notify_title': res_notify_title, 'pass_back': pass_back,
            }
            response = requests.post(
                urljoin(api_url, 'app/asterisk_plus/agent'),
                headers={
                    'x-api-key': api_key,
                    'x-instance-uid': instance_uid,
                }, json=data, timeout=timeout, verify=False)
            response.raise_for_status()
            return res
        except Exception as e:
            if raise_exc:
                if response is None:
                    raise ValidationError(str(e))
                else:
                    raise ValidationError(response.text)
            else:
                logger.exception('Local job error:')            

    def ping_agent(self):
        self.ensure_one()
        try:
            self.local_job(fun='test.ping', res_notify_uid=self.env.user.id,
                res_notify_title='Async', timeout=5)
        except Exception as e:
            raise ValidationError(str(e))
>>>>>>> 3f9693d7298f8d0af34eaf4acc0a50b9a5397b55

    def ami_action(self, action, timeout=5, no_wait=False, as_list=None, **kwargs):
        return self.local_job(
            fun='asterisk.manager_action',
<<<<<<< HEAD
            arg=action,
            kwarg={
=======
            args=action,
            kwargs={
>>>>>>> 3f9693d7298f8d0af34eaf4acc0a50b9a5397b55
                'as_list': as_list
            }, **kwargs)

    def asterisk_ping(self):        
        """Called from server form to test AMI connectivity.
        """
<<<<<<< HEAD
        self.ami_action({'Action': 'Ping'}, res_notify_uid=self.env.user.id)
=======
        try:
            self.ami_action({'Action': 'Ping'}, res_notify_uid=self.env.user.id)
        except Exception as e:
            raise ValidationError(str(e))
>>>>>>> 3f9693d7298f8d0af34eaf4acc0a50b9a5397b55

    @api.model
    def originate_call(self, number, model=None, res_id=None, user=None, dtmf_variables=None):
        """Originate Call with click2dial widget.

          Args:
            number (str): Number to dial.
        """
        # Strip spaces and dash.
        number = number.replace(' ', '')
        number = number.replace('-', '')
        number = number.replace('(', '')
        number = number.replace(')', '')
        debug(self, '{} {} {} {}'.format(number, model, res_id, user))
        if not user:
            user = self.env.user
        if not user.asterisk_users:
            raise ValidationError('PBX User is not defined!') # sdd sd sd sd sdsd sdsd s
        # Format number
        if model and res_id:
            obj = self.env[model].browse(res_id)
            if obj and getattr(obj, '_get_country', False):
                country = obj._get_country()
                number = format_number(self, number, country)
        # Set CallerIDName
        if model and model != 'asterisk_plus.call' and res_id:
            obj = self.env[model].browse(res_id)
            if hasattr(obj, 'name'):
                callerid_name = 'To: {}'.format(obj.name)
        else:
            callerid_name = ''
        # Get originate timeout
        originate_timeout = float(self.env[
            'asterisk_plus.settings'].sudo().get_param('originate_timeout'))

        for asterisk_user in self.env.user.asterisk_users:
            if not asterisk_user.channels:
                raise ValidationError('SIP channels not defined for user!')
            originate_channels = [k for k in asterisk_user.channels if k.originate_enabled]
            if not originate_channels:
                raise ValidationError('No channels with originate enabled!')
            variables = asterisk_user._get_originate_vars()
            for ch in originate_channels:
                channel_vars = variables.copy()
                if ch.auto_answer_header:
                    header = ch.auto_answer_header
                    try:
                        pos = header.find(':')
                        param = header[:pos]
                        val = header[pos+1:]
                        if 'PJSIP' in ch.name.upper():
                            channel_vars.append(
                                'PJSIP_HEADER(add,{})={}'.format(
                                    param.lstrip(), val.lstrip()))
                        else:
                            channel_vars.append(
                                'SIPADDHEADER={}: {}'.format(
                                    param.lstrip(), val.lstrip()))
                    except Exception:
                        logger.warning(
                            'Cannot parse auto answer header: %s', header)

                if dtmf_variables:
                    channel_vars.extend(dtmf_variables)

                channel_id = str(uuid.uuid4())
                other_channel_id = str(uuid.uuid4())
                # Create a call.
                call_data = {
                    'server': asterisk_user.server.id,
                    'uniqueid': channel_id,
                    'calling_user': self.env.user.id,
                    'calling_number': asterisk_user.exten,
                    'called_number': number,
                    'started': datetime.now(),
                    'direction': 'out',
                    'is_active': True,
                    'status': 'progress',
                    'model': model,
                    'res_id': res_id,
                }
                if model == 'res.partner':
                    # Set call partner
                    call_data['partner'] = res_id
                call = self.env['asterisk_plus.call'].create(call_data)
                self.env['asterisk_plus.channel'].create({
                        'server': asterisk_user.server.id,
                        'user': self.env.user.id,
                        'call': call.id,
                        'channel': ch.name,
                        'uniqueid': channel_id,
                        'linkedid': other_channel_id,
                        'is_active': True,
                })
                if not self.env.context.get('no_commit'):
                    self.env.cr.commit()
                action = {
                    'Action': 'Originate',
                    'Context': ch.originate_context,
                    'Priority': '1',
                    'Timeout': 1000 * originate_timeout,
                    'Channel': ch.name,
                    'Exten': number,
                    'Async': 'true',
                    'EarlyMedia': 'true',
                    'CallerID': '{} <{}>'.format(callerid_name, number),
                    'ChannelId': channel_id,
                    'OtherChannelId': other_channel_id,
                    'Variable': channel_vars,
                }
                ch.server.ami_action(action, res_model='asterisk_plus.server',
                                     res_method='originate_call_response',
                                     pass_back={'notify_uid': self.env.user.id,
                                                'channel_id': channel_id})

    @api.model
    def originate_call_response(self, data, channel_id=None, notify_uid=None):
        if data['Response'] == 'Error':
            logger.info('Originate error: %s', data['Message'])
            # Hangup channel.
            call = self.env['asterisk_plus.call'].search(
                [('uniqueid', '=', channel_id)])
            call.write({'status': 'failed', 'is_active': False})
            call.channels.write({'is_active': False})
            self.env['asterisk_plus.settings'].odoopbx_notify(
                'Call to {} failed: {}'.format(
<<<<<<< HEAD
                    call.called_number, data[0]['Message']),
                notify_uid=pass_back['uid'],
=======
                    call.called_number, data['Message']),
                notify_uid=notify_uid,
>>>>>>> 3f9693d7298f8d0af34eaf4acc0a50b9a5397b55
                warning=True)
        return True

<<<<<<< HEAD
    @api.onchange('custom_command')
    def send_custom_command(self):
        try:
            cmd_args_re = re.compile(r'^(.+) \[(.+)\]( {(.+)})?$')
            found = cmd_args_re.search(self.custom_command)
            if not found:
                raise ValidationError("Cannot parse command line!")
            res = self.local_job(
                fun=found.group(1),
                arg=json.loads(found.group(2)),
                kwarg=json.loads(found.group(4) or "{}"),
                sync=True)
            if isinstance(res, str):
                pass
            else:
                res = json.dumps(res, indent=2)
            self.custom_command_reply = res
        except ValueError:
            raise ValidationError('Command not understood! Example: asterisk.manager_action [{"Action":"Ping"}]')

    @api.onchange('connection_mode')
    def _check_cloud_reqs(self):
        if self.connection_mode == 'cloud':
            try:
                import boto3
            except ImportError:
                raise ValidationError('Install boto3 library: pip3 install boto3')

    def cloud_rpc(self, fun, arg=None, kwarg=None, timeout=5,
                  res_model=None, res_method=None, res_notify_uid=None,
                  pass_back=None, sync=False, raise_exc=True):        
        if not CLOUD_CONNECTION:
            raise ValidationError('Install boto3 library: pip3 install boto3')
        # Split fun into service and method
        service, method = fun.split('.')
        if not isinstance(arg, list):
            arg = arg and [arg] or []
        kwarg = kwarg or {}
        # Service mapping to keep compatibility with Salt modules. TODO: Remove it.
        if service == 'asterisk' and ('_config' in method or '_prompt' in method or '_file' in method):
            service = 'file'
        elif service == 'asterisk' and ('_banned' in method or method == 'update_access_rules'):
            service = 'security'
        message = json.dumps({
            'service': service, 'method': method, 'args': arg, 'kwargs': kwarg,
            'timeout': 'timeout', 'res_model': res_model, 'res_method': res_method,
            'res_notify_uid': res_notify_uid, 'pass_back': pass_back, 'sync': sync,
        })
        config = Config(connect_timeout=5, retries={'max_attempts': 0})
        client = boto3.client('sqs', region_name=self.cloud_region,
            config=config,
            aws_access_key_id=self.cloud_access_key,
            aws_secret_access_key=self.cloud_secret_key)
        res = client.send_message(
                QueueUrl=self.cloud_url,
                MessageBody=message)

    def get_agent_config(self):
        res = {}
        server = self.env.user.asterisk_server
        if not server:
            logger.error('Cannot get server by id: %s', server_id)            
        else:
            for k in [
                    'ami_user', 'ami_password', 'ami_host',
                    'ami_port', 'ami_use_tls', 'asterisk_http_url']:
                res[k] = getattr(server, k)
        return res

    def get_cloud_config(self, server_id):
        res = {}
        server = self.env.user.asterisk_server
        if not server:
            logger.error('Cannot get server by id: %s', server_id)            
        elif server.cloud_access_key:
            for k in ['cloud_region', 'cloud_access_key', 'cloud_secret_key', 'cloud_url']:
                res[k] = getattr(server, k)
        return res

    @api.onchange('ami_use_tls')
    def _change_ami_port(self):
        if self.ami_use_tls and self.ami_port == 5038:
            self.ami_port = 5039
        elif not self.ami_use_tls and self.ami_port == 5039:
            self.ami_port = 5038

    @api.model
    def subscription_request(self, url, data, no_error_log=False):
        subscription_server = self.env['ir.config_parameter'].sudo().get_param(
            'asterisk_plus.subscription_server')
        call_url = urljoin(subscription_server, url)
        res = {}
        try:
            r = requests.post(call_url, json=data, timeout=60)
            r.raise_for_status()
            res = r.json().get('result', {})
            error = r.json().get('error', res.get('error', {}))
        except Exception as e:
            if not no_error_log:
                logger.error('Request error: %s', e)
            raise ValidationError('Request error! Try again later or visit odoopbx.com to submit a report!')
        if error:
            raise ValidationError(error['message'])
        return res

    def create_subscription(self, subscription_code, region):
        self.ensure_one()
        # Check if web.base.url is not setup.
        if 'localhost' in self.web_base_url or '127.0.0.1' in self.web_base_url:
            raise ValidationError('Your web.base.url is not setup for the real hostname!')
        # Check that web.base.url is accessible.
        res = self.subscription_request('asterisk_plus_subscription/ping',
            {'web_base_url': self.web_base_url})
        if res.get('error'):
            raise ValidationError(res['error']['message'])
        new_password = generate_strong_password()
        self.user.password = new_password
        data = {
            'database_uuid': self.env['ir.config_parameter'].get_param('database.uuid'),
            'server_id': self.server_id,
            'subscription_code': subscription_code,
            'region': region,
            'environment': {
                'ODOO_URL': self.web_base_url,
                'ODOO_DB': self.db_name,
                'ODOO_USER': self.user.login,
                'ODOO_PASSWORD': new_password,
            },
            'module_version': self.module_version,
            'odoo_version': tools.odoo.release.major_version,
        }
        if self.openvpn_enabled:
            data['openvpn_config'] = self.openvpn_config
            data['environment']['OPENVPN_AUTOSTART'] = True
        res = self.subscription_request('/asterisk_plus_subscription/create',  data)
        self.write({
            'agent_url': res.get('agent_url'),
            'subscription_token': res.get('subscription_token'),
            'subscription_status': 'active',
        })

    def cancel_subscription(self, force_cancel=False):
        self.ensure_one()
        data={
            'database_uuid': self.env['ir.config_parameter'].get_param('database.uuid'),
            'server_id': self.server_id,
            'subscription_token': self.subscription_token,
        }
        try:
            res = self.subscription_request('/asterisk_plus_subscription/delete', data)
        except Exception as e:
            logger.error('Cancel subscription error: %s', e)
            if not force_cancel:
                raise ValidationError('Cannot cancel server! Try again later or visit odoopbx.com to submit a report!\n{}'.format(e))
        self.write({
            'subscription_status': 'new',
            'subscription_token': False,
            'agent_url': False,
        })

    def update_subscription(self):
        self.ensure_one()
        new_password = generate_strong_password()
        self.user.password = new_password
        data={
            'database_uuid': self.env['ir.config_parameter'].get_param('database.uuid'),
            'server_id': self.server_id,
            'subscription_token': self.subscription_token,
            'environment': {
                'ODOO_URL': self.web_base_url,
                'ODOO_DB': self.db_name,
                'ODOO_USER': self.user.login,
                'ODOO_PASSWORD': new_password,
            },
            'module_version': self.module_version,
            'odoo_version': tools.odoo.release.major_version,
        }
        if self.openvpn_enabled:
            data['openvpn_config'] = self.openvpn_config
            data['environment']['OPENVPN_AUTOSTART'] = True
        res = self.subscription_request('/asterisk_plus_subscription/update', data)
        self.agent_url = res['agent_url']


    @api.model
    def check_new_version_on_upgrade(self):
        # Called from xml function.
        try:
            self.env.ref('asterisk_plus.default_server').check_new_version(
                on_update=True, no_error_log=True)
        except: 
            pass

    def check_new_version(self, on_update=False, no_error_log=False):
        self.ensure_one()
        if on_update and not self.subscription_token:
            # Don't check a server without subscription
            return False
        data={
            'subscription_token': self.subscription_token,
            'current_version': self.module_version,
        }
        res = self.subscription_request(
            '/asterisk_plus_subscription/version', data, no_error_log=no_error_log)
        if float(res['latest_version']) > float(self.module_version):
            self.is_module_update = True
        else:
            self.is_module_update = False

    def agent_log_refresh(self):
        self.ensure_one()
        data={
            'database_uuid': self.env['ir.config_parameter'].get_param('database.uuid'),
            'server_id': self.server_id,
            'subscription_token': self.subscription_token,
        }
        res = self.subscription_request('/asterisk_plus_subscription/agent_log', data)
        self.agent_log = res['agent_log']
=======
    @api.onchange('agent_initialized')
    def _check_agent_initialization_open(self):
        if self._origin.agent_initialized and not self.agent_initialized:
            # User wants to enable initialization again.
            if not self.agent_initialization_open:
                raise ValidationError('You must open initialization before removing agent initialized flag!')
>>>>>>> 3f9693d7298f8d0af34eaf4acc0a50b9a5397b55
