import os
from flask import Flask, redirect, render_template, request, url_for
from flask_login import current_user, LoginManager, login_required, logout_user
from flask_migrate import Migrate
from app.models import WebUser
import logging.config
import irods.exception

from . import auth, collbrowser, jobs, docviewer
from . import projects, cluster, admin, reports, userinfo
from . import ngsruns, upload
import irods.exception


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

#Session(app)

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

from .ngsruns import db
db.init_app(app)
migrate = Migrate(app, db)

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

@app.teardown_request
def teardown(x):
    try:
        current_user.irods_session.cleanup()
    except:
        pass

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
    app.logger.warning("Unauthorized access attempt: '{}' on '{}'".format(current_user.get_id()), request.path)
    # Re-raise, since we don't have a solution.
    raise Exception(e)
