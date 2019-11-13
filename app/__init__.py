import os

from flask import Flask
from flask_login import LoginManager, login_required

def create_app(test_config=None):
    # create and configure the app
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY='58gqh)5&^&877838-_P[43889rv4&*F$%q5',
#        DATABASE=os.path.join(app.instance_path, 'flaskr.sqlite'),
    )

    if test_config is None:
        # load the instance config, if it exists, when not testing
        app.config.from_pyfile('config.py', silent=True)
    else:
        # load the test config if passed in
        app.config.from_mapping(test_config)

    # ensure the instance folder exists
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    from . import auth, old
    app.register_blueprint(auth.bp)
    app.register_blueprint(old.bp)
    
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"

    @login_manager.user_loader
    def load_user(userid):
        print(userid)

    # a simple page that says hello
    @app.route('/hello')
    @login_required
    def hello():
        return 'Hello, World!'

    return app