from flask import render_template, Blueprint

resources_blueprint = Blueprint('resources', __name__)

@resources_blueprint.route('/app/<int:app_id>/resources', methods=['GET'])
def resources(app_id: int):
    return render_template('resources/resources.html', app_id=app_id)

@resources_blueprint.route('/app/<int:app_id>/resource/<int:resource_id>', methods=['GET'])
def resource(app_id: int, resource_id: int):
    return render_template('resources/resource.html', app_id=app_id, resource_id=resource_id)
