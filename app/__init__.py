import os

from flask import Flask, render_template
from flask_login import LoginManager, login_required
from app.models import Userstore
from . import auth, old, collbrowser

app = Flask(__name__)

app.config.from_mapping(
        SECRET_KEY='58gqh)5&^&877838-_P[43889rv4&*F$%q5',
#        DATABASE=os.path.join(app.instance_path, 'flaskr.sqlite'),
)

app.register_blueprint(auth.bp)
#app.register_blueprint(old.bp)
app.register_blueprint(collbrowser.bp)

   
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "auth.login"

@login_manager.user_loader
def load_user(userid):
    return Userstore.GetUser(userid)

@app.route('/')
@login_required
def home():
    return render_template('home.html')
