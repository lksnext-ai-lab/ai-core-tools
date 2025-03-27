from flask import Flask, render_template, session, request, redirect, url_for
from flask_restful import Api, Resource
from flask_session import Session
from flask_login import LoginManager, UserMixin, login_required, login_user, logout_user, current_user
from extensions import db, init_db, DATABASE_URL
from flask_openapi3 import OpenAPI
from flask_openapi3 import Info
from services.app_service import AppService
import os
import json
import requests
import uuid
from datetime import timedelta, datetime
from dotenv import load_dotenv

from model.app import App
from model.user import User

from blueprints.agents import agents_blueprint
from blueprints.repositories import repositories_blueprint
from blueprints.resources import resources_blueprint
from blueprints.output_parsers import output_parsers_blueprint
from blueprints.api_keys import api_keys_blueprint
from blueprints.silos import silos_blueprint
from blueprints.domains import domains_blueprint
from blueprints.ai_services import ai_services_blueprint
from blueprints.embeddings_services import embedding_services_blueprint

from api.api import api
from api.silo_api import silo_api
from api.repository_api import repo_api
from api.resource_api import resource_api
from authlib.integrations.flask_client import OAuth


load_dotenv()

info = Info(title="Mattin AI", version="1.0.0")
app = OpenAPI(__name__, info=info, security_schemes={"api_key": {"type": "apiKey", "in": "header", "name": "X-API-KEY"}})

app.secret_key = 'your-secret-key-SXSCDSDASD'
app.config['GOOGLE_CLIENT_ID'] = os.getenv('GOOGLE_CLIENT_ID')
app.config['GOOGLE_CLIENT_SECRET'] = os.getenv('GOOGLE_CLIENT_SECRET')
app.config["GOOGLE_DISCOVERY_URL"] = os.getenv('GOOGLE_DISCOVERY_URL')


app.register_blueprint(agents_blueprint)
app.register_blueprint(repositories_blueprint)
app.register_blueprint(resources_blueprint)
app.register_blueprint(output_parsers_blueprint)
app.register_blueprint(api_keys_blueprint)
app.register_blueprint(silos_blueprint)
app.register_blueprint(ai_services_blueprint)
app.register_blueprint(domains_blueprint)
app.register_blueprint(embedding_services_blueprint)

app.register_api(silo_api)
app.register_api(api)
app.register_api(repo_api)
app.register_api(resource_api)
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL

oauth = OAuth(app)
google = oauth.register(
    name="google",
    client_id=app.config["GOOGLE_CLIENT_ID"],
    client_secret=app.config["GOOGLE_CLIENT_SECRET"],
    server_metadata_url=app.config["GOOGLE_DISCOVERY_URL"],
    client_kwargs={"scope": "openid email profile"},
)

db.init_app(app)

SESSION_TYPE = 'filesystem'
PERMANENT_SESSION_LIFETIME = timedelta(minutes=30)
app.config.from_object(__name__)
Session(app)

with app.app_context():
    init_db()

@app.before_request
def before_request():
    if 'session_id' not in session:
        # Generate a new session ID
        session['session_id'] = str(uuid.uuid4())

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/home')
@login_required
def home():
    apps = AppService.get_apps(current_user.get_id())
    if session.get('app_id') is not None:
        return app_index(session['app_id'])
    return render_template('home.html', apps=apps)

@app.route('/app/<int:app_id>', methods=['GET'])
@login_required
def app_index(app_id: int):
    selected_app = AppService.get_app(app_id)
    session['app_id'] = app_id
    session['app_name'] = selected_app.name
    
    return render_template('app_index.html', app=selected_app)

@app.route('/create-app', methods=['POST'])
@login_required
def create_app():
    name = request.form['name']
    new_app = AppService.create_or_update_app({'name': name, 'user_id': current_user.get_id()})
    return app_index(new_app.app_id)

#@app.route('/leave')
@app.route('/my-apps')
@login_required
def my_apps():
    session.pop('app_id', None)
    session.pop('app_name', None)
    return home()

@app.route('/delete-app/<int:app_id>', methods=['GET'])
@login_required
def delete_app(app_id: int):
    AppService.delete_app(app_id)
    return redirect(url_for('home'))


@app.route("/login")
def login():
    nonce = uuid.uuid4().hex 
    session["oauth_nonce"] = nonce
    return google.authorize_redirect(url_for("auth_callback", _external=True), nonce=nonce)



@app.route('/callback')
def auth_callback():
    token = google.authorize_access_token()
    access_token = token.get("access_token")

    if not access_token:
        return "Error: Access token not found!", 400

    user_info_endpoint = "https://www.googleapis.com/oauth2/v1/userinfo"
    user_info = google.get(user_info_endpoint, token=token).json()

    if not user_info:
        return "Error: Unable to fetch user info!", 400
    
    session["user"] = user_info 

    user = db.session.query(User).filter_by(email=user_info['email']).first()
    if not user:
        user = User(email=user_info['email'], name=user_info['name'])
        db.session.add(user)
        db.session.commit()
    
    session['user_id'] = user.user_id
    login_user(user)

    return redirect(url_for('home'))
    

@app.route('/logout')
def logout():
    '''Logout user'''
    session.clear()
    return redirect(url_for('index'))

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return db.session.query(User).get(int(user_id))

@app.route('/about')
def about():
    return render_template('about.html')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=4321, debug=True)

