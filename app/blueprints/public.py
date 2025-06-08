from flask import Blueprint, render_template

public_blueprint = Blueprint('public', __name__, url_prefix='/')

@public_blueprint.route('/product')
def product():
    """Product information page"""
    return render_template('public/product.html')

@public_blueprint.route('/features')
def features():
    """Features showcase page"""
    return render_template('public/features.html')

@public_blueprint.route('/pricing')
def pricing():
    """Pricing plans page"""
    return render_template('public/pricing.html')

@public_blueprint.route('/solutions')
def solutions():
    """Solutions and use cases page"""
    return render_template('public/solutions.html')

@public_blueprint.route('/documentation')
def documentation():
    """Public documentation page"""
    return render_template('public/documentation.html')

@public_blueprint.route('/support')
def support():
    """Support and contact page"""
    return render_template('public/support.html')

@public_blueprint.route('/privacy')
def privacy():
    """Privacy policy page"""
    return render_template('public/privacy.html')

@public_blueprint.route('/terms')
def terms():
    """Terms of service page"""
    return render_template('public/terms.html')

@public_blueprint.route('/about')
def about():
    """About us page"""
    return render_template('public/about.html') 