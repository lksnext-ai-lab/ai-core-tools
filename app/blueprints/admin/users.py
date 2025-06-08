from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from services.user_service import UserService
from flask_paginate import Pagination, get_page_args

admin_users_blueprint = Blueprint('admin_users', __name__, url_prefix='/admin/users')

@admin_users_blueprint.route('/')
@login_required
def list_users():
    """List all users with pagination"""
    page, per_page, offset = get_page_args(page_parameter='page', per_page_parameter='per_page')
    per_page = 10  # Number of users per page
    
    users, total = UserService.get_all_users(page=page, per_page=per_page)
    
    pagination = Pagination(page=page, per_page=per_page, total=total, css_framework='bootstrap5')
    
    return render_template('admin/users/list.html', users=users, pagination=pagination)

@admin_users_blueprint.route('/<int:user_id>')
@login_required
def view_user(user_id):
    """View user details"""
    user = UserService.get_user_by_id(user_id)
    if not user:
        flash('User not found', 'error')
        return redirect(url_for('admin_users.list_users'))
    
    return render_template('admin/users/view.html', user=user)

@admin_users_blueprint.route('/<int:user_id>/delete', methods=['POST'])
@login_required
def delete_user(user_id):
    """Delete a user and all associated data"""
    try:
        user = UserService.get_user_by_id(user_id)
        if not user:
            flash('User not found', 'error')
            return redirect(url_for('admin_users.list_users'))
        
        user_name = user.name or user.email
        success = UserService.delete_user(user_id)
        
        if success:
            flash(f'User {user_name} and all associated data have been deleted successfully', 'success')
        else:
            flash(f'Error deleting user {user_name}', 'error')
            
    except Exception as e:
        flash(f'Error deleting user: {str(e)}', 'error')
    
    return redirect(url_for('admin_users.list_users'))

@admin_users_blueprint.route('/search')
@login_required
def search_users():
    """Search users by name or email"""
    query = request.args.get('q', '').strip()
    page, per_page, offset = get_page_args(page_parameter='page', per_page_parameter='per_page')
    per_page = 10
    
    if query:
        users, total = UserService.search_users(query, page=page, per_page=per_page)
    else:
        users, total = UserService.get_all_users(page=page, per_page=per_page)
    
    pagination = Pagination(page=page, per_page=per_page, total=total, css_framework='bootstrap5')
    
    return render_template('admin/users/list.html', users=users, pagination=pagination, search_query=query) 