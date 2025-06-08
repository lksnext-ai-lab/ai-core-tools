from flask import Blueprint, render_template, abort
import os

public_blueprint = Blueprint('public', __name__, url_prefix='/')

def check_service_mode():
    """Check if public pages are allowed (only in service mode)"""
    aict_mode = os.getenv('AICT_MODE', 'ONLINE')
    if aict_mode == 'SELF-HOSTED':
        abort(404)  # Return 404 for self-hosted installations

def check_online_mode_only():
    """Check if public pages are allowed (only in ONLINE mode, not in SELF-HOSTED)"""
    aict_mode = os.getenv('AICT_MODE', 'ONLINE')
    if aict_mode == 'SELF-HOSTED':
        abort(404)  # Return 404 for self-hosted installations

@public_blueprint.route('/product')
def product():
    """Product information page - allowed in both modes"""
    # Product page is allowed in both ONLINE and SELF-HOSTED modes
    return render_template('public/product.html')

@public_blueprint.route('/features')
def features():
    """Features showcase page"""
    check_online_mode_only()
    return render_template('public/features.html')

@public_blueprint.route('/pricing')
def pricing():
    """Pricing plans page"""
    check_online_mode_only()
    return render_template('public/pricing.html')

@public_blueprint.route('/solutions')
def solutions():
    """Solutions and use cases page"""
    check_online_mode_only()
    return render_template('public/solutions.html')

@public_blueprint.route('/documentation')
def documentation():
    """Public documentation page"""
    check_online_mode_only()
    return render_template('public/documentation.html')

@public_blueprint.route('/support')
def support():
    """Support and contact page"""
    check_online_mode_only()
    return render_template('public/support.html')

@public_blueprint.route('/privacy')
def privacy():
    """Privacy policy page"""
    check_online_mode_only()
    return render_template('public/privacy.html')

@public_blueprint.route('/terms')
def terms():
    """Terms of service page"""
    check_online_mode_only()
    return render_template('public/terms.html')

@public_blueprint.route('/about')
def about():
    """About us page"""
    check_online_mode_only()
    return render_template('public/about.html') 