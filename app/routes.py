from flask import Blueprint
import logging
import requests
from requests.auth import HTTPBasicAuth
from flask import jsonify, render_template, request, current_app
from flask_login import current_user, login_required
import subprocess
from app.auth import auth_endpoint
from .irodssessions import irods_manager
from .constants import FEATURES

from .flaskcache import cache
from . import messages
from . import auth


bp = Blueprint('main', __name__, url_prefix=None)


REQUESTS_METHODS = {
    'GET':   requests.get,
    'PUT':   requests.put,
    'POST':  requests.post,
    'DELETE':requests.delete
}



@bp.route('/')
@login_required
def home():
    newsitems = messages.load_messages(category='home', only_current=True)
    return render_template('home.html', newsitems=newsitems)

@bp.route('/api/msgconfirm', methods=['POST'])
def msgconfirm():
    messages.confirm()
    return dict(result='OK')

@bp.route('/about')
def about():
    ngsweb_version = subprocess.check_output(["git", "rev-parse", "HEAD"]).strip().decode('utf-8')
    ngsweb_branch = subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"]).strip().decode('utf-8')
    with irods_manager.session() as session:
        irods_version = '.'.join(map(str, session.server_version))
    return render_template('about.html', irods_version=irods_version, ngsweb_version=ngsweb_version, ngsweb_branch=ngsweb_branch)


@bp.route('/settings')
def settings():
    features = []
    for feature, feature_properties in FEATURES.items():
        description, default = feature_properties
        features.append({
            'label': feature,
            'description': description,
            'value': current_user.feature(feature)
        })

    return render_template('settings.html', features=features)


@bp.route('/_brs/<path:rest_endpoint>', methods=['GET', 'PUT', 'POST', 'DELETE'])
@auth_endpoint
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
    if (hostname := current_app.config.get('API_HOST')) is None:
        hostname = current_user.irods_server        
    url = 'http://{}/api/1.0/{}'.format(hostname, rest_endpoint)
    auth = HTTPBasicAuth(current_user.username, current_user.password)
    return_data = {}
    if request.method in REQUESTS_METHODS:
        response = REQUESTS_METHODS[request.method](url, auth=auth, json=data)
    try:
        return_data = response.json()
    except:
        return_data = {}
    if request.method != 'GET':
        #cache is defined as global in flaskcache.py
        cache.delete_memoized(restcall)
    return jsonify(return_data), response.status_code    

