from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from services.app_service import AppService
from extensions import db

app_settings_blueprint = Blueprint('app_settings', __name__)

@app_settings_blueprint.route('/app/<int:app_id>/settings', methods=['GET', 'POST'])
@login_required
def app_settings(app_id):
    """View and edit app settings"""
    app = AppService.get_app(app_id)
    if not app:
        flash('App not found', 'error')
        return redirect(url_for('my_apps'))
    
    # Set session variables for the template (needed by app_settings_base.html)
    from flask import session
    session['app_id'] = app_id
    session['app_name'] = app.name
    
    if request.method == 'POST':
        try:
            app_data = {
                'app_id': app_id,
                'name': request.form.get('name'),
                'langsmith_api_key': request.form.get('langsmith_api_key')
            }
            AppService.create_or_update_app(app_data)
            flash('Settings updated successfully', 'success')
            return redirect(url_for('app_settings.app_settings', app_id=app_id))
        except Exception:
            flash('An error occurred while updating settings', 'error')
    
    return render_template('app_settings/settings.html', app=app) 