from functools import wraps
from flask import session, jsonify, flash, redirect, url_for, request
from services.subscription_service import SubscriptionService
from utils.config import is_self_hosted
import logging

logger = logging.getLogger(__name__)

def require_plan(min_plan='free'):
    """Decorator to require a minimum plan level"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Skip all checks in self-hosted mode
            if is_self_hosted():
                return f(*args, **kwargs)
                
            if not session.get('user_id'):
                flash('Please log in to access this feature', 'error')
                return redirect(url_for('login'))
            
            user_id = session['user_id']
            subscription_info = SubscriptionService.get_user_subscription_info(user_id)
            
            if not subscription_info:
                flash('Unable to verify subscription', 'error')
                return redirect(url_for('home'))
            
            current_plan = subscription_info['plan']['name']
            plan_hierarchy = {'free': 0, 'starter': 1, 'enterprise': 2}
            
            if plan_hierarchy.get(current_plan, 0) < plan_hierarchy.get(min_plan, 0):
                flash(f'This feature requires a {min_plan.title()} plan or higher', 'warning')
                return redirect(url_for('public.pricing'))
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def require_feature(feature_name):
    """Decorator to require a specific feature"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Skip all checks in self-hosted mode
            if is_self_hosted():
                return f(*args, **kwargs)
                
            if not session.get('user_id'):
                flash('Please log in to access this feature', 'error')
                return redirect(url_for('login'))
            
            user_id = session['user_id']
            if not SubscriptionService.check_feature_access(user_id, feature_name):
                flash(f'This feature is not available in your current plan', 'warning')
                return redirect(url_for('public.pricing'))
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def check_usage_limit(resource_type):
    """Decorator to check usage limits before allowing action"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Skip all checks in self-hosted mode
            if is_self_hosted():
                return f(*args, **kwargs)
                
            if not session.get('user_id'):
                if request.is_json:
                    return jsonify({'error': 'Authentication required'}), 401
                flash('Please log in to access this feature', 'error')
                return redirect(url_for('login'))
            
            user_id = session['user_id']
            usage_check = SubscriptionService.check_usage_limits(user_id, resource_type)
            
            if not usage_check['allowed']:
                message = f'Usage limit exceeded for {resource_type}'
                if usage_check.get('limit') != 'unlimited':
                    message += f" ({usage_check.get('current', 0)}/{usage_check.get('limit', 0)})"
                
                if request.is_json:
                    return jsonify({
                        'error': message,
                        'current': usage_check.get('current', 0),
                        'limit': usage_check.get('limit', 0),
                        'upgrade_url': url_for('public.pricing')
                    }), 403
                
                flash(message + '. Please upgrade your plan to continue.', 'warning')
                return redirect(url_for('public.pricing'))
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def subscription_required(f):
    """Decorator to ensure user has an active subscription"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Skip all checks in self-hosted mode
        if is_self_hosted():
            return f(*args, **kwargs)
            
        if not session.get('user_id'):
            flash('Please log in to access this feature', 'error')
            return redirect(url_for('login'))
        
        user_id = session['user_id']
        subscription_info = SubscriptionService.get_user_subscription_info(user_id)
        
        if not subscription_info or subscription_info['subscription']['status'] not in ['active', 'trial']:
            flash('Active subscription required', 'warning')
            return redirect(url_for('public.pricing'))
        
        return f(*args, **kwargs)
    return decorated_function

def check_api_usage_limit(resource_type):
    """Decorator to check usage limits for API calls at subscription level (works with API key authentication and session-based authentication)"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Skip all checks in self-hosted mode
            if is_self_hosted():
                return f(*args, **kwargs)
                
            from models.api_key import APIKey
            from models.user import User
            from models.api_usage import APIUsage
            from db.database import SessionLocal, db
            
            user = None
            
            # Try API key authentication first
            api_key = request.headers.get('X-API-KEY')
            if api_key:
                # Find the API key and get the user
                session_db = SessionLocal()
                try:
                    api_key_obj = session_db.query(APIKey).filter_by(key=api_key, is_active=True).first()
                    if not api_key_obj:
                        return jsonify({'error': 'Invalid API key'}), 401
                    
                    user = session_db.query(User).filter_by(user_id=api_key_obj.user_id).first()
                    if not user:
                        return jsonify({'error': 'User not found'}), 401
                finally:
                    session_db.close()
            else:
                # Fall back to session-based authentication (for playground calls)
                if not session.get('user_id'):
                    return jsonify({'error': 'Authentication required - API key or session required'}), 401
                
                session_db = SessionLocal()
                try:
                    user = session_db.query(User).filter_by(user_id=session['user_id']).first()
                    if not user:
                        return jsonify({'error': 'User not found'}), 401
                finally:
                    session_db.close()
            
            # Get user's subscription and plan
            subscription = user.subscription
            if not subscription or not subscription.is_active:
                return jsonify({'error': 'No active subscription'}), 403
            
            plan = subscription.plan
            if not plan:
                return jsonify({'error': 'No active subscription plan'}), 403
            
            # For API calls, track at subscription level
            if resource_type == 'api_calls':
                # Get the limit for this plan
                limit = getattr(plan, 'max_api_calls_per_month', 0)
                if limit == -1:  # Unlimited
                    return f(*args, **kwargs)
                
                try:
                    # Get or create current month's usage record
                    usage_record = APIUsage.get_or_create_current_usage(
                        user_id=user.user_id,
                        subscription_id=subscription.subscription_id
                    )
                    
                    # Check current usage before incrementing
                    current_usage = usage_record.api_calls_count
                    if current_usage >= limit:
                        return jsonify({
                            'error': f'API usage limit exceeded. Plan allows {limit} calls per month.',
                            'current_usage': current_usage,
                            'limit': limit,
                            'message': 'Please upgrade your plan to continue'
                        }), 429
                    
                    # Atomically increment the counter
                    new_count = usage_record.increment_api_calls()
                    
                    # Store usage info in request for potential use
                    request.api_usage = {
                        'current': new_count,
                        'limit': limit,
                        'remaining': limit - new_count
                    }
                    
                except Exception as e:
                    logger.error(f"Failed to track API usage: {e}")
                    return jsonify({'error': 'Failed to track API usage'}), 500
            else:
                # For other resources, use the original logic
                usage_check = SubscriptionService.check_usage_limits(user.user_id, resource_type)
                
                if not usage_check['allowed']:
                    return jsonify({
                        'error': f'Usage limit exceeded for {resource_type}',
                        'current': usage_check.get('current', 0),
                        'limit': usage_check.get('limit', 0),
                        'message': 'Please upgrade your plan to continue'
                    }), 403
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator 