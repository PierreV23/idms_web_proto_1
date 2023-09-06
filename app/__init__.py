from logging import FileHandler
import json
import os
import requests
import dateutil.parser
from datetime import datetime
from requests.auth import HTTPBasicAuth
from flask import Flask, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, LoginManager, login_required, logout_user
from flask_migrate import Migrate
from app.models import WebUser, AuthException
import logging.config
import irods.exception
import subprocess
from Crypto.PublicKey import RSA

from . import auth, collbrowser, jobs, docviewer
from . import projects, cluster, admin, reports, userinfo
from . import ngsruns, upload, flaskcache
from . import messages, oldjobs
from .ngsruns import db as ngsruns_db, NGSRunsDBUnavailableException
from .jobs import db as jobs_db, JobsDBUnavailableException
from .flaskcache import cache, dep_zone
from .irodssessions import irods_manager

# This is the default log config. It can (and should) be overruled by
# setting LOGCONFIG in config.py
DEFAULT_LOGCONFIG = {
    'version': 1,
    'formatters': {'default': {'format': '[%(asctime)s] %(levelname)s - %(module)s: %(message)s'}},
    'handlers': {'default': {'class': 'logging.StreamHandler', 'formatter': 'default'}},
    'root': {'level': 'DEBUG', 'handlers': ['default']}
}

app = Flask(__name__)

# Default config; N.B. values may be overridden by loading instance config.py below.
app.config.from_mapping(
    SECRET_KEY='58gqh)5&^&877838-_P[43889rv4&*F$%q5',
#    DATABASE=os.path.join(app.instance_path, 'ngsrun.sqlite'),
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    SQLALCHEMY_DATABASE_URI='sqlite:///{}/ngsruns.sqlite'.format(app.instance_path),
)

app.config.from_pyfile(os.path.join(app.instance_path, 'config.py'), silent=True)
app.config.from_pyfile(os.path.join(app.instance_path, 'constants.py'), silent=True)

logging.config.dictConfig(app.config.get('LOGCONFIG', DEFAULT_LOGCONFIG))

def init_dbs():
    ngsruns_db.init_app(app)
    jobs_db.init_app(app)
    irods_manager.init_app(app)

# When running under uwsgi, the postfork decorator is required
# for the database connections
try:
    from uwsgidecorators import postfork
    postfork(init_dbs)
except ModuleNotFoundError:
    init_dbs()

def create_keys():
    key = RSA.generate(2048)
    private_key = key.export_key()
    file_out = open(os.path.join(app.instance_path, "private.pem"), "wb")
    file_out.write(private_key)
    file_out.close()

    public_key = key.publickey().export_key()
    file_out = open(os.path.join(app.instance_path, "receiver.pem"), "wb")
    file_out.write(public_key)
    file_out.close()

try:
    public_key = RSA.import_key(open("instance/receiver.pem").read())
    private_key = RSA.import_key(open("instance/private.pem").read())
except:
    create_keys()
    public_key = RSA.import_key(open("instance/receiver.pem").read())
    private_key = RSA.import_key(open("instance/private.pem").read())

app.config.from_mapping(
    RSA_PRIVATE_KEY=private_key,
    RSA_PUBLIC_KEY=public_key,
)

app.register_blueprint(auth.bp)
app.register_blueprint(collbrowser.bp)
app.register_blueprint(jobs.bp)
app.register_blueprint(docviewer.BP)
app.register_blueprint(projects.BP)
app.register_blueprint(cluster.bp)
app.register_blueprint(admin.bp)
app.register_blueprint(reports.bp)
app.register_blueprint(ngsruns.bp)
app.register_blueprint(upload.bp)
app.register_blueprint(userinfo.bp)
app.register_blueprint(oldjobs.bp)


flaskcache.init(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "auth.login"

logging.info('NGSWEB initialized')

@login_manager.user_loader
def load_user(userid):
    return WebUser.retrieve(userid)

@app.route('/')
@login_required
def home():
    return render_template('home.html')

@app.route('/api/msgconfirm', methods=['POST'])
def msgconfirm():
    messages.confirm()
    return dict(result='OK')

@app.route('/about')
def about():
    ngsweb_version = subprocess.check_output(["git", "rev-parse", "HEAD"]).strip().decode('utf-8')
    ngsweb_branch = subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"]).strip().decode('utf-8')
    with irods_manager.session() as session:
        irods_version = '.'.join(map(str, session.server_version))
    return render_template('about.html', irods_version=irods_version, ngsweb_version=ngsweb_version, ngsweb_branch=ngsweb_branch)

REQUESTS_METHODS = {
    'GET':   requests.get,
    'PUT':   requests.put,
    'POST':  requests.post,
    'DELETE':requests.delete
}

@app.route('/_brs/<path:rest_endpoint>', methods=['GET', 'PUT', 'POST', 'DELETE'])
@login_required
def restcall(rest_endpoint):
    """Proxy endpoint for bio-rest service

    Args:
        rest_endpoint (str): Endpoint path

    Returns:
        tuple: data, result_code
    """    
    if request.method in ('PUT', 'POST'):
        data = request.json
    else:
        data = None
    url = 'http://{}/api/1.0/{}'.format(current_user.irods_server, rest_endpoint)
    #TODO: remove this testing line:
    #url = 'http://{}/api/1.0/{}'.format('0.0.0.0:5000', rest_endpoint)
    auth = HTTPBasicAuth('alt\\{}'.format(current_user.username), current_user.ntlm_hash)
    return_data = {}
    if request.method in REQUESTS_METHODS:
        response = REQUESTS_METHODS[request.method](url, auth=auth, json=data)
    try:
        return_data = response.json()
    except:
        return_data = {}
    if request.method != 'GET':
        cache.delete_memoized(restcall)
    return jsonify(return_data), response.status_code    

@cache.memoize(timeout=600, make_name=dep_zone)
def get_header_messages():
    if not hasattr(current_user, 'irods_zone'):
        return ''
    all_messages = []
    messageobject = os.path.join('/', current_user.irods_zone, app.config.get("HEADER_MESSAGE_OBJECT","none"))
    try:
        if current_user.ifs.fileexists(messageobject):
            obj = current_user.ifs.getfile(messageobject)
            messages_json = obj.open('r').read().decode('utf-8')
            all_messages = json.loads(messages_json).get('messages', [])
    except Exception as ex:
        # Do not break the website if the message file has an invalid format
        pass
    messages = []
    for msg in all_messages:
        valid_msg = True
        try:
            if (ts := msg.get("start")):
                if dateutil.parser.isoparse(ts) > datetime.now():
                    valid_msg = False
            if (ts := msg.get("end")):
                if dateutil.parser.isoparse(ts) < datetime.now():
                    valid_msg = False
            if valid_msg:
                messages.append(msg)
        except:
            # skip message with invalid time fields
            pass
    return messages

@app.context_processor
def inject_header_message():
    header_messages = get_header_messages()
    return dict(header_messages=header_messages)

# @app.teardown_request
# def teardown(x):
#     try:
#         current_user.irods_session.cleanup()
#     except:
#         pass

@app.errorhandler(irods.exception.PAM_AUTH_PASSWORD_FAILED)
def invalid_session1(e):
    """Session may be stale. Destroy it and redirect to login page."""
    app.logger.info(f"Invalid session: user {current_user.username} on {current_user.environment} environment")
    return auth.logout()

@app.errorhandler(irods.exception.NetworkException)
def invalid_session2(e):
    """Session may be stale. Destroy it and redirect to login page."""
    app.logger.info(f"Invalid session: user {current_user.username} on {current_user.environment} environment")
    return auth.logout()

@app.errorhandler(AuthException)
def auth_failed(e):
    """Destroy session and redirect to login page."""
    app.logger.info(f"Auth Error: user {current_user.username} on {current_user.environment} environment")
    return auth.logout()

# irods.exception.CAT_NO_ACCESS_PERMISSION
@app.errorhandler(irods.exception.CAT_NO_ACCESS_PERMISSION)
def unauthorized(e):
    """Log trial of access to object or collection for which user has no 
    authorization."""
    # N.B. we can't extract the object that was accessed (tried to) from 
    # the exception, so just log the request path instead.
    app.logger.warning("Unauthorized access attempt: '{}' on '{}'".format(current_user.get_id(), request.path))
    # Re-raise, since we don't have a solution.
    raise Exception(e)

@app.errorhandler(NGSRunsDBUnavailableException)
def handle_bad_ngsruns_request(e):
    flash('NGSRuns Database Unavailable', 'error')
    return redirect(url_for('home'))

@app.errorhandler(JobsDBUnavailableException)
def handle_bad_jobs_request(e):
    flash('Jobs table unavailable. Reverting to old jobs view ...', 'error')
    return redirect(url_for('oldjobs.show_jobs'))
