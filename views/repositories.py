from flask import Flask, render_template, session, Blueprint
from model.repository import Repository

repositories_blueprint = Blueprint('repositories', __name__)

@repositories_blueprint.route('/app/<app_id>/repositories', methods=['GET'])
def repositories(app_id):
    repos = Repository.query.filter_by(app_id=app_id).all()
    return render_template('repositories/repositories.html', repos=repos)

@repositories_blueprint.route('/app/<app_id>/repository/<repository_id>', methods=['GET'])
def repository(app_id, repository_id):
    repo = Repository.query.filter_by(repository_id=repository_id).first()
    return render_template('repositories/repository.html', app_id=app_id, repo=repo)

@repositories_blueprint.route('/app/<app_id>/repository/<repository_id>/playground', methods=['GET'])
def repository_playground(app_id, repository_id):
    repo = Repository.query.filter_by(repository_id=repository_id).first()
    return render_template('repositories/playground.html', app_id=app_id, repo=repo)
