from flask import Flask, render_template, session
from flask_restful import Api, Resource
from extensions import db
import os
import json

from model.app import App
from flask import jsonify

from views.resources import resources_blueprint
from views.repositories import repositories_blueprint

app = Flask(__name__)

app.register_blueprint(resources_blueprint)
app.register_blueprint(repositories_blueprint)

MYSQL_USER = os.getenv("MYSQL_USER")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD")
MYSQL_HOST = os.getenv("MYSQL_HOST")
MYSQL_SCHEMA = os.getenv("MYSQL_SCHEMA")

app.secret_key = 'your-secret-key-SXSCDSDASD'
app.config[
    'SQLALCHEMY_DATABASE_URI'] = f"mysql://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}/{MYSQL_SCHEMA}"
db.init_app(app)


@app.route('/')
def index():
    apps = App.query.all()
    if session.get('app_id') is not None:
        return app_index(session['app_id'])
    return render_template('index.html', apps=apps)

@app.route('/app/<app_id>', methods=['GET'])
def app_index(app_id):
    app = App.query.filter_by(app_id=app_id).first()
    session['app_id'] = app_id
    session['app_name'] = app.name
    
    return render_template('app_index.html', app=app)

@app.route('/leave')
def leave():
    session.pop('app_id', None)
    session.pop('app_name', None)
    return index()


if __name__ == '__main__':
    app.run(debug=True)

