from functools import wraps
from flask import flash, redirect, url_for, request
from flask_login import login_required, current_user
from services.app_service import AppService
from services.app_collaboration_service import AppCollaborationService
from utils.logger import get_logger

logger = get_logger(__name__)

def validate_app_access(f):
    """
    Decorator to validate that the current user has access to the specified app.
    Expects the route to have an 'app_id' parameter.
    
    Usage:
        @blueprint.route('/app/<int:app_id>/some-route')
        @login_required
        @validate_app_access
        def some_route(app_id: int, app=None):
            # app parameter will contain the validated App object
            return render_template('template.html', app=app)
    
    Features:
        - Validates that the app exists in the database
        - Checks if the current user has access to the app
        - Automatically redirects to home with error messages if validation fails
        - Passes the validated app object to the decorated function
        - Handles app_id from URL parameters, request.args, or request.form
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        app_id = kwargs.get('app_id')
        if app_id is None:
            # Try to get app_id from request.args or request.form
            app_id = request.args.get('app_id') or request.form.get('app_id')
            if app_id:
                app_id = int(app_id)
        
        if app_id is None:
            flash('App ID is required.', 'error')
            return redirect(url_for('home'))
        
        # Validate app exists
        app = AppService.get_app(app_id)
        if not app:
            flash('App not found.', 'error')
            return redirect(url_for('home'))
        
        # Validate user has access
        user_id = int(current_user.get_id())
        if not AppCollaborationService.can_user_access_app(user_id, app_id):
            flash('You do not have access to this app.', 'error')
            return redirect(url_for('home'))
        
        # Add app to kwargs for the decorated function
        kwargs['app'] = app
        return f(*args, **kwargs)
    
    return decorated_function

def require_app_management(f):
    """
    Decorator to validate that the current user can manage the specified app.
    Expects the route to have an 'app_id' parameter.
    
    Usage:
        @blueprint.route('/app/<int:app_id>/admin-settings')
        @login_required
        @require_app_management
        def admin_settings(app_id: int, app=None):
            # Only app owners and managers can access this route
            return render_template('admin_settings.html', app=app)
    
    Features:
        - Validates that the app exists in the database
        - Checks if the current user can manage the app (owner or manager)
        - Automatically redirects to home with error messages if validation fails
        - Passes the validated app object to the decorated function
        - More restrictive than validate_app_access
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        app_id = kwargs.get('app_id')
        if app_id is None:
            app_id = request.args.get('app_id') or request.form.get('app_id')
            if app_id:
                app_id = int(app_id)
        
        if app_id is None:
            flash('App ID is required.', 'error')
            return redirect(url_for('home'))
        
        # Validate app exists
        app = AppService.get_app(app_id)
        if not app:
            flash('App not found.', 'error')
            return redirect(url_for('home'))
        
        # Validate user can manage the app
        user_id = int(current_user.get_id())
        if not AppCollaborationService.can_user_manage_app(user_id, app_id):
            flash('You do not have permission to manage this app.', 'error')
            return redirect(url_for('home'))
        
        # Add app to kwargs for the decorated function
        kwargs['app'] = app
        return f(*args, **kwargs)
    
    return decorated_function 