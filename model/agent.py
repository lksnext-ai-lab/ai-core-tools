from extensions import db


class Agent(db.Model):
    __tablename__ = 'Agent'
    agent_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255))
    description = db.Column(db.String(1000))
    system_prompt = db.Column(db.Text)
    prompt_template = db.Column(db.Text)
    type = db.Column(db.String(45))
    status = db.Column(db.String(45))
    model = db.Column(db.String(45))
    model_id = db.Column(db.Integer,
                        db.ForeignKey('Model.model_id'),
                        nullable=True)
    repository_id = db.Column(db.Integer,
                        db.ForeignKey('Repository.repository_id'),
                        nullable=True)
    app_id = db.Column(db.Integer,
                        db.ForeignKey('App.app_id'),
                        nullable=True)
    
    model = db.relationship('Model',
                           foreign_keys=[model_id])
    

    reopository = db.relationship('Repository',
                           back_populates='agents',
                           foreign_keys=[repository_id])

    app = db.relationship('App',
                           back_populates='agents',
                           foreign_keys=[app_id])
    
