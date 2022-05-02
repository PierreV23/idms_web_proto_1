import os
import requests
from requests.auth import HTTPBasicAuth
from flask import Flask, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, LoginManager, login_required, logout_user
from flask_migrate import Migrate
from app.models import WebUser
import logging.config
import irods.exception

from . import auth, collbrowser, jobs, docviewer
from . import projects, cluster, admin, reports, userinfo
from . import ngsruns, upload, flaskcache
from . import messages
from .ngsruns import db, NGSRunsDBUnavailableException
from .flaskcache import cache


logging.config.dictConfig({
    'version': 1,
    'handlers': {
        'wsgi': {
            'class': 'logging.StreamHandler',
        },
        'syslog': {
            'class': 'logging.handlers.SysLogHandler'
        }
    },
    'root': {
        'level': 'DEBUG',
        'handlers': ['wsgi', 'syslog']
    }
})

app = Flask(__name__)

# Default config; N.B. values may be overridden by loading instance config.py below.
app.config.from_mapping(
    SECRET_KEY='58gqh)5&^&877838-_P[43889rv4&*F$%q5',
#    DATABASE=os.path.join(app.instance_path, 'ngsrun.sqlite'),
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    SQLALCHEMY_DATABASE_URI='sqlite:///{}/ngsruns.sqlite'.format(app.instance_path),
# Use serverside session , seems logical to use SQLALCHEMY for session management
# needed to store stateful Nonacris object during Kiemsurveillance upload
# TODO: create necessary tables and switch to sqlalchemy...
# However: the NncWeb-Object cant be 'pickled' (serialized?) since it contains the database connection: 
#     mssql.MSSQLConnection.__reduce_cython__
#     TypeError: no default __reduce__ due to non-trivial __cinit__
#    SESSION_TYPE= 'filesystem'  #'sqlalchemy'
)

app.config.from_pyfile(os.path.join(app.instance_path, 'config.py'), silent=True)
app.config.from_pyfile(os.path.join(app.instance_path, 'constants.py'), silent=True)

db.init_app(app)

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


flaskcache.init(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "auth.login"

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

@app.route('/contacts')
def contacts():
    return render_template('contacts.html')

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


# @app.teardown_request
# def teardown(x):
#     try:
#         current_user.irods_session.cleanup()
#     except:
#         pass

@app.errorhandler(irods.exception.PAM_AUTH_PASSWORD_FAILED)
def invalid_session(e):
    """Session may be stale. Destroy it and redirect to login page."""
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
def handle_bad_request(e):
    flash('NGSRuns Database Unavailable', 'error')
    return redirect(url_for('home'))
