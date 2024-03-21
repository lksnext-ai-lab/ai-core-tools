from flask import Flask, render_template, session, Blueprint

resources_blueprint = Blueprint('resources', __name__)

@resources_blueprint.route('/app/<app_id>/resources', methods=['GET'])
def resources(app_id):
    return render_template('resources/resources.html', app_id=app_id)

@resources_blueprint.route('/app/<app_id>/resource/<resource_id>', methods=['GET'])
def resource(app_id, resource_id):
    return render_template('resources/resource.html', app_id=app_id, resource_id=resource_id)
