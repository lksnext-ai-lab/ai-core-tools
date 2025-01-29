from flask import render_template, Blueprint, request, redirect, url_for
from app.extensions import db
from app.model.model import Model
models_blueprint = Blueprint('models', __name__, url_prefix='/admin/models')

@models_blueprint.route('/', methods=['GET'])
def models():
    models = Model.query.all()
    return render_template('models/models.html', models=models)

