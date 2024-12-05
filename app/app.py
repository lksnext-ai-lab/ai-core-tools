from flask import Flask, render_template, session, request
from flask_restful import Api, Resource
from flask_session import Session
from app.extensions import db, init_db

import os
import json
from datetime import timedelta, datetime
from dotenv import load_dotenv

from app.model.app import App
from flask import jsonify

from app.api.api import api_blueprint
from app.views.agents import agents_blueprint
from app.views.repositories import repositories_blueprint
from app.views.resources import resources_blueprint
from app.views.output_parsers import output_parsers_blueprint
import uuid

load_dotenv()

app = Flask(__name__)
app.secret_key = 'your-secret-key-SXSCDSDASD'

app.register_blueprint(agents_blueprint)
app.register_blueprint(repositories_blueprint)
app.register_blueprint(resources_blueprint)
app.register_blueprint(api_blueprint)
app.register_blueprint(output_parsers_blueprint)

app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv("SQLALCHEMY_DATABASE_URI")

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
    apps = db.session.query(App).all()
    if session.get('app_id') is not None:
        return app_index(session['app_id'])
    return render_template('index.html', apps=apps)

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
    return index()


if __name__ == '__main__':
    app.run(debug=True)

