from flask import Blueprint, request, render_template
from app.services.output_parser_service import OutputParserService

output_parsers_blueprint = Blueprint('output_parsers', __name__)
parser_service = OutputParserService()

@output_parsers_blueprint.route('/app/<int:app_id>/output-parsers', methods=['GET'])
def app_output_parsers(app_id: int):
    parsers = parser_service.get_parsers_by_app(app_id)
    return render_template('output_parsers/output_parsers.html', 
                         parsers=parsers, 
                         app_id=app_id)

@output_parsers_blueprint.route('/app/<int:app_id>/output-parser/<int:parser_id>', methods=['GET', 'POST'])
def app_output_parser(app_id: int, parser_id: int):
    if request.method == 'POST':
        data = {
            'name': request.form['name'],
            'description': request.form.get('description'),
            'app_id': app_id,
            'field_names': request.form.getlist('field_name'),
            'field_types': request.form.getlist('field_type'),
            'field_descriptions': request.form.getlist('field_description'),
            'list_item_types': request.form.getlist('list_item_type')
        }
        parser_service.create_or_update_parser(parser_id, data)
        return app_output_parsers(app_id)

    parser = parser_service.get_parser_by_id(parser_id) if parser_id != 0 else None
    available_parsers = parser_service.get_parsers_by_app(app_id)
    
    return render_template('output_parsers/output_parser.html',
                         app_id=app_id,
                         parser=parser or {'parser_id': 0, 'name': ''},
                         available_parsers=available_parsers)

@output_parsers_blueprint.route('/app/<int:app_id>/output-parser/<int:parser_id>/delete', methods=['GET'])
def app_output_parser_delete(app_id: int, parser_id: int):
    parser_service.delete_parser(parser_id)
    return app_output_parsers(app_id) 