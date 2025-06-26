from model.api_key import APIKey
from extensions import db
from datetime import datetime
from functools import wraps
from flask import request, jsonify, session
from model.app import App
from services.app_collaboration_service import AppCollaborationService
import os
    
# Authentication helper functions
def is_omniadmin(email):
    if not email:
        return False
    omniadmins = os.getenv('AICT_OMNIADMINS', '').split(',')
    return email in omniadmins

def is_valid_api_key(app_id, api_key):
    if api_key is None:
        return False
    
    api_key_obj = db.session.query(APIKey).filter(
        APIKey.app_id == app_id,
        APIKey.key == api_key,
        APIKey.is_active == True
    ).first()
    
    if api_key_obj is None:
        return False
    
    api_key_obj.last_used_at = datetime.now()
    db.session.commit()
    return True

def check_session_permission(app_id):
    """Check if current user can access the app (owner or collaborator)"""
    if session.get('user') is None:
        return False
    
    user_id = int(session.get('user_id'))
    return AppCollaborationService.can_user_access_app(user_id, int(app_id))

def check_owner_permission(app_id):
    """Check if current user is the owner of the app"""
    if session.get('user') is None:
        return False
    
    user_id = int(session.get('user_id'))
    return AppCollaborationService.can_user_manage_app(user_id, int(app_id))

def require_auth(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Try to get app_id from different possible sources
        app_id = None
        
        # First try: direct app_id parameter (used by collaboration routes)
        if 'app_id' in kwargs:
            app_id = kwargs['app_id']
        # Second try: path.app_id (used by other API routes)
        elif 'path' in kwargs and kwargs['path'] is not None:
            app_id = kwargs['path'].app_id
        else:
            return jsonify({"error": "Unauthorized - App ID not found"}), 401
        
        api_key = request.headers.get('X-API-KEY')
        
        if not check_session_permission(app_id) and not is_valid_api_key(app_id, api_key):
            return jsonify({"error": "Unauthorized - Invalid or missing API key"}), 401
            
        return f(*args, **kwargs)
    return decorated_function

def require_owner_auth(f):
    """Decorator that requires the user to be the app owner"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Try to get app_id from different possible sources
        app_id = None
        
        # First try: direct app_id parameter (used by collaboration routes)
        if 'app_id' in kwargs:
            app_id = kwargs['app_id']
        # Second try: path.app_id (used by other API routes)
        elif 'path' in kwargs and kwargs['path'] is not None:
            app_id = kwargs['path'].app_id
        else:
            return jsonify({"error": "Unauthorized - App ID not found"}), 401
        
        api_key = request.headers.get('X-API-KEY')
        
        # For API key auth, we still allow access (API keys are app-specific)
        if is_valid_api_key(app_id, api_key):
            return f(*args, **kwargs)
        
        # For session auth, check if user is the owner
        if not check_owner_permission(app_id):
            return jsonify({"error": "Unauthorized - Owner access required"}), 403
            
        return f(*args, **kwargs)
    return decorated_function