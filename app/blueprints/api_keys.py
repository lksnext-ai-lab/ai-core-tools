from flask import Blueprint, render_template, request, flash, redirect, url_for, session
from flask_login import login_required, current_user
from services.api_key_service import APIKeyService
from utils.logger import get_logger
from utils.error_handlers import handle_web_errors, AppError

logger = get_logger(__name__)

CREATE_TEMPLATE = 'api_keys.create_api_key'
LIST_TEMPLATE = 'api_keys.list_api_keys'
api_keys_blueprint = Blueprint('api_keys', __name__, url_prefix='/api_keys')


@api_keys_blueprint.route('/')
@login_required
@handle_web_errors(redirect_url=LIST_TEMPLATE)
def list_api_keys():
    """List all API keys belonging to the current user"""
    app_id = session.get('app_id')
    user_id = current_user.get_id()
    
    logger.info(f"User {user_id} accessing API keys for app {app_id}")
    
    # Get API keys using the service
    api_keys = APIKeyService.get_api_keys_by_app(app_id, user_id)
    
    return render_template('api_keys/api_key_list.html', api_keys=api_keys)


@api_keys_blueprint.route('/create', methods=['GET', 'POST'])
@login_required
@handle_web_errors(redirect_url=CREATE_TEMPLATE)
def create_api_key():
    """Create a new API key"""
    if request.method == 'POST':
        name = request.form.get('name')
        app_id = session.get('app_id')
        user_id = current_user.get_id()
        
        logger.info(f"User {user_id} creating API key '{name}' for app {app_id}")
        
        # Create API key using the service
        api_key = APIKeyService.create_api_key(name, app_id, user_id)
        
        flash('API key created successfully', 'success')
        logger.info(f"Successfully created API key {api_key.key_id} for user {user_id}")
        return redirect(url_for(LIST_TEMPLATE))
    
    return render_template('api_keys/create.html')


@api_keys_blueprint.route('/<int:key_id>/delete', methods=['POST'])
@login_required
@handle_web_errors(redirect_url=LIST_TEMPLATE)
def delete_api_key(key_id):
    """Delete an API key"""
    user_id = current_user.get_id()
    
    logger.info(f"User {user_id} deleting API key {key_id}")
    
    # Delete API key using the service
    APIKeyService.delete_api_key(key_id, user_id)
    
    flash('API key deleted successfully', 'success')
    logger.info(f"Successfully deleted API key {key_id} for user {user_id}")
    return redirect(url_for(LIST_TEMPLATE))


@api_keys_blueprint.route('/<int:key_id>/toggle', methods=['POST'])
@login_required
@handle_web_errors(redirect_url=LIST_TEMPLATE)
def toggle_api_key(key_id):
    """Toggle API key active status"""
    user_id = current_user.get_id()
    
    logger.info(f"User {user_id} toggling API key {key_id}")
    
    # Toggle API key using the service
    updated_key = APIKeyService.toggle_api_key(key_id, user_id)
    
    status = 'activated' if updated_key.is_active else 'deactivated'
    flash(f'API key {status} successfully', 'success')
    logger.info(f"Successfully {status} API key {key_id} for user {user_id}")
    
    return redirect(url_for(LIST_TEMPLATE))
