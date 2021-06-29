import os
from flask import Flask, redirect, render_template, url_for
from flask_login import current_user, LoginManager, login_required, logout_user
from flask_migrate import Migrate
from app.models import WebUser
from . import auth, collbrowser, jobs, docviewer
from . import projects, cluster, admin, reports, userinfo
from . import ngsruns, upload
import irods.exception

app = Flask(__name__)

# Default config; N.B. values may be overridden by loading instance config.py below.
app.config.from_mapping(
    SECRET_KEY='58gqh)5&^&877838-_P[43889rv4&*F$%q5',
#    DATABASE=os.path.join(app.instance_path, 'ngsrun.sqlite'),
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    SQLALCHEMY_DATABASE_URI='sqlite:///{}/ngsruns.sqlite'.format(app.instance_path)
)

app.config.from_pyfile(os.path.join(app.instance_path, 'config.py'), silent=True)



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
