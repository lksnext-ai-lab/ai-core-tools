from flask import Blueprint, render_template, request, flash, redirect, url_for
from flask_login import login_required, current_user
from model.api_key import APIKey
from model.app import App
from extensions import db
import secrets
import string
from datetime import datetime
from flask import session

api_keys_blueprint = Blueprint('api_keys', __name__, url_prefix='/api_keys')

def generate_api_key(length=48):
    """Generate a secure random API key"""
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))

@api_keys_blueprint.route('/')
@login_required
def list_api_keys():
    """List all API keys belonging to the current user"""
    print("app id: ", session['app_id'])
    api_keys = db.session.query(APIKey).filter_by(app_id=session['app_id']).all()
    return render_template('api_keys/api_key_list.html', api_keys=api_keys)

@api_keys_blueprint.route('/create', methods=['GET', 'POST'])
@login_required
def create_api_key():
    """Create a new API key"""
    if request.method == 'POST':
        name = request.form.get('name')
        app_id = session['app_id']
        
        if not name or not app_id:
            flash('Name and App are required', 'error')
            return redirect(url_for('api_keys.create_api_key'))
        
        # Verify app exists and user has access to it
        app = db.session.query(App).filter_by(app_id=app_id).first()
        if not app or app.user_id != current_user.get_id():
            flash('Invalid app selected', 'error')
            return redirect(url_for('api_keys.create_api_key'))
        
        api_key = APIKey(
            key=generate_api_key(),
            name=name,
            app_id=app_id,
            user_id=current_user.get_id()
        )
        
        try:
            db.session.add(api_key)
            db.session.commit()
            flash('API key created successfully', 'success')
            return redirect(url_for('api_keys.list_api_keys'))
        except Exception as e:
            db.session.rollback()
            flash('Error creating API key', 'error')
            return redirect(url_for('api_keys.create_api_key'))
    
    
    return render_template('api_keys/create.html')


@api_keys_blueprint.route('/<int:key_id>/delete', methods=['POST'])
@login_required
def delete_api_key(key_id):
    """Delete an API key"""
    api_key = db.session.query(APIKey).filter_by(key_id=key_id, user_id=current_user.get_id()).first()
    if not api_key:
        flash('API key not found', 'error')
        return redirect(url_for('api_keys.list_api_keys'))
    
    try:
        db.session.delete(api_key)
        db.session.commit()
        flash('API key deleted successfully', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Error deleting API key', 'error')
    
    return redirect(url_for('api_keys.list_api_keys'))

@api_keys_blueprint.route('/<int:key_id>/toggle', methods=['POST'])
@login_required
def toggle_api_key(key_id):
    """Toggle API key active status"""
    api_key = db.session.query(APIKey).filter_by(key_id=key_id, user_id=current_user.get_id()).first()
    if not api_key:
        flash('API key not found', 'error')
        return redirect(url_for('api_keys.list_api_keys'))
    
    try:
        api_key.is_active = not api_key.is_active
        db.session.commit()
        status = 'activated' if api_key.is_active else 'deactivated'
        flash(f'API key {status} successfully', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Error toggling API key status', 'error')
    
    return redirect(url_for('api_keys.list_api_keys'))
