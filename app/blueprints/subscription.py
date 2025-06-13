from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from services.subscription_service import SubscriptionService
from utils.pricing_decorators import require_plan
from flask import session

subscription_blueprint = Blueprint('subscription', __name__, url_prefix='/subscription')

@subscription_blueprint.route('/')
@login_required
def dashboard():
    """Subscription dashboard"""
    user_id = session['user_id']
    subscription_info = SubscriptionService.get_user_subscription_info(user_id)
    all_plans = SubscriptionService.get_all_plans()
    
    return render_template('subscription/dashboard.html', 
                         subscription_info=subscription_info,
                         all_plans=all_plans)

@subscription_blueprint.route('/upgrade/<plan_name>')
@login_required
def upgrade(plan_name):
    """Upgrade to a specific plan"""
    user_id = session['user_id']
    
    try:
        if plan_name == 'starter':
            # Start trial for starter plan
            subscription = SubscriptionService.upgrade_subscription(user_id, plan_name, is_trial=True)
            flash(f'Successfully started 14-day trial for {plan_name.title()} plan!', 'success')
        elif plan_name == 'enterprise':
            flash('Please contact sales for Enterprise plan', 'info')
            return redirect(url_for('public.support'))
        else:
            subscription = SubscriptionService.upgrade_subscription(user_id, plan_name)
            flash(f'Successfully upgraded to {plan_name.title()} plan!', 'success')
        
        return redirect(url_for('subscription.dashboard'))
    
    except ValueError as e:
        flash(str(e), 'error')
        return redirect(url_for('public.pricing'))

@subscription_blueprint.route('/cancel', methods=['POST'])
@login_required
def cancel():
    """Cancel current subscription"""
    user_id = session['user_id']
    # Implement cancellation logic
    flash('Subscription cancelled successfully', 'success')
    return redirect(url_for('subscription.dashboard'))

@subscription_blueprint.route('/usage-api')
@login_required
def usage_api():
    """API endpoint for usage information"""
    user_id = session['user_id']
    subscription_info = SubscriptionService.get_user_subscription_info(user_id)
    return jsonify(subscription_info) 