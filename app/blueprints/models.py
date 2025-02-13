from flask import render_template, Blueprint, request, redirect, url_for
from app.extensions import db
from app.model.model import Model
models_blueprint = Blueprint('models', __name__, url_prefix='/admin/models')

@models_blueprint.route('/', methods=['GET'])
def models():
    models = db.session.query(Model).all()
    return render_template('models/models.html', models=models)

@models_blueprint.route('/<int:model_id>', methods=['GET'])
def model(model_id):
    model = db.session.query(Model).get(model_id)
    return render_template('models/model.html', model=model)

