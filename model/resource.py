from extensions import db


class Resource(db.Model):
    __tablename__ = 'Resource'
    resource_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255))
    uri = db.Column(db.String(1000))
    type = db.Column(db.String(45))
    status = db.Column(db.String(45))
    app_id = db.Column(db.Integer,
                        db.ForeignKey('App.app_id'),
                        nullable=True)


    app = db.relationship('App',
                           back_populates='resources',
                           foreign_keys=[app_id])

