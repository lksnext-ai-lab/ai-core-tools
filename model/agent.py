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
    repository_id = db.Column(db.Integer,
                        db.ForeignKey('Repository.repository_id'),
                        nullable=True)
    


    reopository = db.relationship('Repository',
                           back_populates='agents',
                           foreign_keys=[repository_id])

