'''App model class'''
from extensions import db

class App(db.Model):
    '''User model class constructor'''
    __tablename__ = 'App'
    app_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255))

    resources = db.relationship('Resource', backref='app_resources', lazy=True)