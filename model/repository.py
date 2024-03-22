from extensions import db


class Repository(db.Model):
    __tablename__ = 'Repository'
    repository_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255))
    type = db.Column(db.String(45))
    status = db.Column(db.String(45))
    app_id = db.Column(db.Integer,
                        db.ForeignKey('App.app_id'),
                        nullable=True)


    app = db.relationship('App',
                           back_populates='repositories',
                           foreign_keys=[app_id])
    
    resources = db.relationship('Resource', backref='repository_resources', lazy=True)
    agents = db.relationship('Agent', backref='repository_agents', lazy=True)

