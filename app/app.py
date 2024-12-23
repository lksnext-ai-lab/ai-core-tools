from flask import Flask, render_template, session, request, jsonify, redirect, url_for
from flask_restful import Api, Resource
from flask_session import Session

from app.extensions import db, init_db, DATABASE_URL

import os
import json
import requests
import uuid
from datetime import timedelta, datetime
from dotenv import load_dotenv

from app.model.app import App
from app.model.user import User

from app.api.api import api_blueprint
from app.views.agents import agents_blueprint
from app.views.repositories import repositories_blueprint
from app.views.resources import resources_blueprint
from app.views.output_parsers import output_parsers_blueprint

from authlib.integrations.flask_client import OAuth


load_dotenv()

app = Flask(__name__)
app.secret_key = 'your-secret-key-SXSCDSDASD'
app.config['GOOGLE_CLIENT_ID'] = os.getenv('GOOGLE_CLIENT_ID')
app.config['GOOGLE_CLIENT_SECRET'] = os.getenv('GOOGLE_CLIENT_SECRET')
app.config["GOOGLE_DISCOVERY_URL"] = os.getenv('GOOGLE_DISCOVERY_URL')


app.register_blueprint(agents_blueprint)
app.register_blueprint(repositories_blueprint)
app.register_blueprint(resources_blueprint)
app.register_blueprint(api_blueprint)
app.register_blueprint(output_parsers_blueprint)

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

# Después de configurar la app y antes de ejecutarla
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
def home():
    apps = db.session.query(App).filter(App.user_id == session['user_id']).all()
    if session.get('app_id') is not None:
        return app_index(session['app_id'])
    return render_template('home.html', apps=apps)

@app.route('/app/<int:app_id>', methods=['GET'])
def app_index(app_id: int):
    app = db.session.query(App).filter(App.app_id == app_id).first()
    session['app_id'] = app_id
    session['app_name'] = app.name
    
    return render_template('app_index.html', app=app)

@app.route('/create-app', methods=['POST'])
def create_app():
    name = request.form['name']
    app = App(name=name)
    db.session.add(app)
    db.session.commit()
    db.session.refresh(app)
    return app_index(app.app_id)

@app.route('/leave')
def leave():
    session.pop('app_id', None)
    session.pop('app_name', None)
    return home()


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

    # Use the access token to fetch user info
    user_info_endpoint = "https://www.googleapis.com/oauth2/v1/userinfo"
    user_info = google.get(user_info_endpoint, token=token).json()

    if not user_info:
        return "Error: Unable to fetch user info!", 400
    
    session["user"] = user_info 

    print(session["user"])

    user = db.session.query(User).filter_by(email=user_info['email']).first()
    if not user:
        db.session.add(User(email=user_info['email'], name=user_info['name']))
        db.session.commit()
    session['user_id'] = user.user_id
    #login_user(SessionUser(user.user_id))


    return redirect(url_for('home'))
    

@app.route('/logout')
def logout():
    '''Logout user'''
    session.clear()
    return redirect(url_for('index'))



if __name__ == '__main__':
    app.run(host='0.0.0.0', port=4321)

