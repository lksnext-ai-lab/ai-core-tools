# App Access Validation Decorators

This document explains how to use the app access validation decorators to secure your Flask routes.

## Overview

The decorators provide a clean, reusable way to validate app access across all blueprints. They handle:
- App existence validation
- User access permissions
- Automatic error handling and redirects
- Session management for deleted apps

## Available Decorators

### `@validate_app_access`
Validates that the current user has access to the specified app.

**Use when:** The user needs to view or interact with app resources.

### `@require_app_management`
Validates that the current user can manage the specified app (owner or manager).

**Use when:** The user needs to modify app settings, delete resources, or perform administrative actions.

## Usage Examples

### Basic Usage

```python
from flask import Blueprint, render_template
from flask_login import login_required
from utils.decorators import validate_app_access

blueprint = Blueprint('example', __name__)

@blueprint.route('/app/<int:app_id>/dashboard')
@login_required
@validate_app_access
def dashboard(app_id: int, app=None):
    # app parameter contains the validated App object
    return render_template('dashboard.html', app=app)
```

### With Management Permissions

```python
@blueprint.route('/app/<int:app_id>/settings')
@login_required
@require_app_management
def settings(app_id: int, app=None):
    # Only app owners and managers can access this
    return render_template('settings.html', app=app)
```

### Combining with Other Decorators

```python
from utils.pricing_decorators import check_usage_limit

@blueprint.route('/app/<int:app_id>/premium-feature')
@login_required
@validate_app_access
@check_usage_limit('premium_feature')
def premium_feature(app_id: int, app=None):
    return render_template('premium.html', app=app)
```

## Implementation in Blueprints

### Before (Manual Validation)
```python
@blueprint.route('/app/<int:app_id>/resources')
def resources(app_id: int):
    # Manual validation
    app = AppService.get_app(app_id)
    if not app:
        flash('App not found.', 'error')
        return redirect(url_for('home'))
    
    user_id = int(current_user.get_id())
    if not AppCollaborationService.can_user_access_app(user_id, app_id):
        flash('You do not have access to this app.', 'error')
        return redirect(url_for('home'))
    
    return render_template('resources.html', app=app)
```

### After (With Decorator)
```python
@blueprint.route('/app/<int:app_id>/resources')
@login_required
@validate_app_access
def resources(app_id: int, app=None):
    return render_template('resources.html', app=app)
```

## Benefits

1. **Cleaner Code**: Eliminates repetitive validation logic
2. **Consistent Security**: All routes use the same validation logic
3. **Automatic Error Handling**: Standardized error messages and redirects
4. **Session Management**: Handles deleted apps gracefully
5. **Reusability**: Easy to apply to any route with app_id parameter

## Migration Guide

To migrate existing routes:

1. **Add imports**:
   ```python
   from flask_login import login_required
   from utils.decorators import validate_app_access
   ```

2. **Add decorators**:
   ```python
   @login_required
   @validate_app_access
   ```

3. **Update function signature**:
   ```python
   def your_function(app_id: int, app=None):
   ```

4. **Remove manual validation code**

5. **Use the app parameter** instead of querying the database again

## Error Handling

The decorators automatically handle:
- Missing app_id
- Non-existent apps
- Insufficient permissions
- Database errors

All errors redirect to the home page with appropriate flash messages.

## Session Management

The decorators work with the session validation in `app.py` to provide comprehensive session management:
- Detects when apps are deleted
- Clears outdated session data
- Prevents URL generation errors
- Provides user-friendly error messages 