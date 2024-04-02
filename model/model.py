'''App model class'''
from extensions import db

class Model(db.Model):
    '''User model class constructor'''
    __tablename__ = 'Model'
    model_id = db.Column(db.Integer, primary_key=True)
    provider = db.Column(db.String(45))
    name = db.Column(db.String(45))
    description = db.Column(db.String(1000))

