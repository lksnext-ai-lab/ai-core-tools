from app.model.api_key import APIKey
from app.extensions import db
from datetime import datetime
from functools import wraps
from flask import request, jsonify, session
from app.model.app import App
    
# Authentication helper functions
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
    if session.get('user') is None:
        return False
    
    app = db.session.query(App).filter(
        App.app_id == int(app_id),
        App.user_id == int(session.get('user_id'))
    ).first()
    
    return app is not None

def require_auth(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        app_id = kwargs.get('path').app_id
        api_key = request.headers.get('X-API-KEY')
        
        if not check_session_permission(app_id) and not is_valid_api_key(app_id, api_key):
            return jsonify({"error": "Unauthorized - Invalid or missing API key"}), 401
            
        return f(*args, **kwargs)
    return decorated_function