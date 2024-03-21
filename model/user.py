'''User model class'''
from extensions import db

class User(db.Model):
    '''User model class constructor'''
    user_id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255))
    name = db.Column(db.String(255))
    #domains = db.relationship('Domain', backref='user', lazy=True)
