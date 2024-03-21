from extensions import db


class Resource(db.Model):
    __tablename__ = 'Resource'
    resource_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255))
    uri = db.Column(db.String(1000))
    type = db.Column(db.String(45))
    status = db.Column(db.String(45))
    repository_id = db.Column(db.Integer,
                        db.ForeignKey('Repository.repository_id'),
                        nullable=True)


    reopository = db.relationship('Repository',
                           back_populates='resources',
                           foreign_keys=[repository_id])

