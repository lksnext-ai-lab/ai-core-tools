from flask import Blueprint, render_template
from flask_login import login_required
from services.user_service import UserService
from model.app import App
from model.agent import Agent
from model.api_key import APIKey
from extensions import db

admin_stats_blueprint = Blueprint('admin_stats', __name__, url_prefix='/admin/stats')

@admin_stats_blueprint.route('/')
@login_required
def dashboard():
    """Admin dashboard with system statistics"""
    
    # Get user stats from UserService
    user_stats = UserService.get_user_stats()
    
    # Get other basic counts
    total_apps = db.session.query(App).count()
    total_agents = db.session.query(Agent).count()
    total_api_keys = db.session.query(APIKey).count()
    active_api_keys = db.session.query(APIKey).filter(APIKey.is_active == True).count()
    
    stats = {
        'total_users': user_stats['total_users'],
        'total_apps': total_apps,
        'total_agents': total_agents,
        'total_api_keys': total_api_keys,
        'active_api_keys': active_api_keys,
        'inactive_api_keys': total_api_keys - active_api_keys,
        'recent_users': user_stats['recent_users'],
        'users_with_apps': user_stats['users_with_apps']
    }
    
    return render_template('admin/stats/dashboard.html', stats=stats) 