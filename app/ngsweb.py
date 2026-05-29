#from logging import FileHandler
import os
import redis
from flask import Flask, redirect, url_for, request, flash
from flask_login import LoginManager
from flask_session import Session
from cachelib.file import FileSystemCache

from .components import contacts_manager, docviewer
from .utils import auth, cluster, flaskcache
from app.utils.webuser import WebUser
import logging.config
import irods.exception
from Crypto.PublicKey import RSA
from app.utils.webuser import AuthException
from .ngsruns import NGSRunsDBUnavailableException
from .utils.database import ICATDBUnavailableException

from . import collbrowser, routes, jobs, messages
from . import projects, admin, reports, userinfo, referencedatasets
from . import ngsruns, upload, search, metaedit, irods_api
from .ngsruns import db as ngsruns_db
from .utils.database import db as jobs_db
from idms.common.irods.irods_sessions import irods_manager
from .branding import get_branding


#from app.stats import statstore

# This is the default log config. It can (and should) be overruled by
# setting LOGCONFIG in config.py
DEFAULT_LOGCONFIG = {
    'version': 1,
    'formatters': {'default': {'format': '[%(asctime)s] %(levelname)s - %(module)s: %(message)s'}},
    'handlers': {'default': {'class': 'logging.StreamHandler', 'formatter': 'default'}},
    'root': {'level': 'DEBUG', 'handlers': ['default']}
}


def create_app():
    app = Flask(__name__, instance_relative_config=True)

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

    # Setup session storage
    if app.config.get('CACHE_TYPE') == 'RedisCache':
        app.config['SESSION_TYPE'] = 'redis'
        hostname = app.config.get('CACHE_REDIS_HOST', 'localhost')
        app.config['SESSION_REDIS'] = redis.Redis.from_url(f'redis://{hostname}:6379')
    else:
        app.config['SESSION_TYPE'] = 'cachelib'
        app.config['SESSION_CACHELIB'] = FileSystemCache(cache_dir='flask_session', threshold=500)
    Session(app)

    # When running under uwsgi, the postfork decorator is required
    # for the database connections
    try:
        from uwsgidecorators import postfork
        @postfork
        def init_dbs_wrapper():
            init_dbs(app)
        init_dbs_wrapper()
    except ModuleNotFoundError:
        init_dbs( app )


    try:
        public_key = RSA.import_key(open("instance/receiver.pem").read())
        private_key = RSA.import_key(open("instance/private.pem").read())
    except:
        create_keys(app)
        public_key = RSA.import_key(open("instance/receiver.pem").read())
        private_key = RSA.import_key(open("instance/private.pem").read())

    app.config.from_mapping(
        RSA_PRIVATE_KEY=private_key,
        RSA_PUBLIC_KEY=public_key,
    )

    app.register_blueprint(routes.bp)
    app.register_blueprint(auth.bp)
    app.register_blueprint(collbrowser.bp)
    app.register_blueprint(jobs.bp)
    app.register_blueprint(docviewer.bp)
    app.register_blueprint(projects.bp)
    app.register_blueprint(referencedatasets.bp)
    app.register_blueprint(cluster.bp)
    app.register_blueprint(admin.bp)
    app.register_blueprint(reports.bp)
    app.register_blueprint(ngsruns.bp)
    app.register_blueprint(upload.bp)
    app.register_blueprint(userinfo.bp)
    app.register_blueprint(messages.bp)
    app.register_blueprint(search.bp)
    app.register_blueprint(metaedit.bp)
    app.register_blueprint(contacts_manager.bp)
    app.register_blueprint(irods_api.bp)

    flaskcache.init(app)

    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"

    @login_manager.user_loader
    def load_user(userid):
        return WebUser.retrieve(userid)
    
    @app.context_processor
    def inject_branding():
        return dict(branding=get_branding(app))

    @app.context_processor
    def inject_header_message():
        header_messages = messages.load_messages(category='banner', only_current=True)
        return dict(header_messages=header_messages)
    
    errorhandlers(app)

    logging.info('iDMS initialized')
    return app

def errorhandlers(app):
    @app.errorhandler(irods.exception.PAM_AUTH_PASSWORD_FAILED)
    def invalid_session0(e):
        """Session may be stale. Destroy it and redirect to login page."""
        logging.info("Invalid session")
        return auth.logout()

    @app.errorhandler(irods.exception.CAT_INVALID_AUTHENTICATION)
    def invalid_session1(e):
        """Session may be stale. Destroy it and redirect to login page."""
        logging.info("Invalid session")
        return auth.logout()

    @app.errorhandler(AuthException)
    def auth_failed(e):
        """Destroy session and redirect to login page."""
        logging.info("Auth Exception")
        return redirect(url_for('auth.login', next=request.full_path))

    @app.errorhandler(AttributeError)
    def handle_attribute_error(e):
        """Destroy session and redirect to login page."""
        logging.exception(f"AttributeError: {e}")
        return redirect(url_for('auth.login', next=request.full_path))  

    @app.errorhandler(NGSRunsDBUnavailableException)
    def handle_bad_ngsruns_request(e):
        flash('NGSRuns Database Unavailable', 'error')
        return redirect(url_for('main.home'))

    @app.errorhandler(irods.exception.CAT_INVALID_USER)
    def invalid_user(e):
        """Connection to iRODS failing. Redirect to login page"""
        logging.info("Invalid user")
        return auth.logout()


def init_dbs(app):
    ngsruns_db.init_app(app)
    jobs_db.init_app(app)
    irods_manager.init_app(app.config.get('IRODS_ENVS', {}), 
                            app.config.get('conn_refresh_time', 120))


def create_keys(app):
    key = RSA.generate(2048)
    private_key = key.export_key()
    file_out = open(os.path.join(app.instance_path, "private.pem"), "wb")
    file_out.write(private_key)
    file_out.close()

    public_key = key.publickey().export_key()
    file_out = open(os.path.join(app.instance_path, "receiver.pem"), "wb")
    file_out.write(public_key)
    file_out.close()


