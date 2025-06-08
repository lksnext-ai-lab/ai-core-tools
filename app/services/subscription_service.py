from model.subscription import Subscription, Plan, SubscriptionStatus
from model.user import User
from extensions import db
from datetime import datetime, timedelta
from typing import Optional, List
import logging

logger = logging.getLogger(__name__)

class SubscriptionService:
    
    @staticmethod
    def initialize_default_plans():
        """Initialize default pricing plans"""
        plans_data = [
            {
                'name': 'free',
                'display_name': 'Free',
                'price': 0.00,
                'max_agents': 2,
                'max_storage_gb': 1,
                'max_domains': 1,
                'max_api_calls_per_month': 1000,
                'has_priority_support': False,
                'has_advanced_analytics': False,
                'has_team_collaboration': False,
                'has_custom_integrations': False,
                'has_on_premise': False
            },
            {
                'name': 'starter',
                'display_name': 'Starter',
                'price': 29.00,
                'max_agents': 10,
                'max_storage_gb': 10,
                'max_domains': 5,
                'max_api_calls_per_month': 50000,
                'has_priority_support': True,
                'has_advanced_analytics': True,
                'has_team_collaboration': True,
                'has_custom_integrations': True,
                'has_on_premise': False
            },
            {
                'name': 'enterprise',
                'display_name': 'Enterprise',
                'price': 0.00,  # Custom pricing
                'max_agents': -1,  # Unlimited
                'max_storage_gb': -1,  # Unlimited
                'max_domains': -1,  # Unlimited
                'max_api_calls_per_month': -1,  # Unlimited
                'has_priority_support': True,
                'has_advanced_analytics': True,
                'has_team_collaboration': True,
                'has_custom_integrations': True,
                'has_on_premise': True
            }
        ]
        
        for plan_data in plans_data:
            existing_plan = db.session.query(Plan).filter_by(name=plan_data['name']).first()
            if not existing_plan:
                plan = Plan(**plan_data)
                db.session.add(plan)
        
        db.session.commit()
        logger.info("Default plans initialized")
    
    @staticmethod
    def create_free_subscription(user_id: int) -> Subscription:
        """Create a free subscription for a new user"""
        free_plan = db.session.query(Plan).filter_by(name='free').first()
        if not free_plan:
            raise ValueError("Free plan not found")
        
        subscription = Subscription(
            user_id=user_id,
            plan_id=free_plan.plan_id,
            status=SubscriptionStatus.ACTIVE
        )
        
        db.session.add(subscription)
        db.session.commit()
        logger.info(f"Created free subscription for user {user_id}")
        return subscription
    
    @staticmethod
    def upgrade_subscription(user_id: int, plan_name: str, is_trial: bool = False) -> Subscription:
        """Upgrade user's subscription to a new plan"""
        user = db.session.query(User).get(user_id)
        if not user:
            raise ValueError("User not found")
        
        new_plan = db.session.query(Plan).filter_by(name=plan_name).first()
        if not new_plan:
            raise ValueError(f"Plan {plan_name} not found")
        
        # Cancel existing active subscriptions
        for subscription in user.subscriptions:
            if subscription.is_active:
                subscription.status = SubscriptionStatus.CANCELLED
                subscription.cancelled_at = datetime.utcnow()
        
        # Create new subscription
        subscription = Subscription(
            user_id=user_id,
            plan_id=new_plan.plan_id,
            status=SubscriptionStatus.TRIAL if is_trial else SubscriptionStatus.ACTIVE,
            is_trial=is_trial
        )
        
        if is_trial:
            subscription.trial_ends_at = datetime.utcnow() + timedelta(days=14)
        
        db.session.add(subscription)
        db.session.commit()
        logger.info(f"Upgraded user {user_id} to {plan_name} plan")
        return subscription
    
    @staticmethod
    def check_feature_access(user_id: int, feature: str) -> bool:
        """Check if user has access to a specific feature"""
        user = db.session.query(User).get(user_id)
        if not user:
            return False
        
        current_subscription = user.subscription
        if not current_subscription or not current_subscription.is_active:
            return False
        
        plan = current_subscription.plan
        return getattr(plan, f'has_{feature}', False)
    
    @staticmethod
    def check_usage_limits(user_id: int, resource: str) -> dict:
        """Check user's usage against their plan limits"""
        user = db.session.query(User).get(user_id)
        if not user:
            return {'allowed': False, 'reason': 'User not found'}
        
        plan = user.current_plan
        
        if resource == 'agents':
            # Count agents across all user's apps
            current_count = 0
            for app in user.apps:
                if hasattr(app, 'agents'):
                    current_count += len(app.agents)
            
            limit = plan.max_agents
            if limit == -1:  # Unlimited
                return {'allowed': True, 'current': current_count, 'limit': 'unlimited'}
            return {
                'allowed': current_count < limit,
                'current': current_count,
                'limit': limit,
                'remaining': max(0, limit - current_count)
            }
        
        elif resource == 'domains':
            # Count domains across all user's apps
            from model.domain import Domain
            current_count = 0
            for app in user.apps:
                if hasattr(app, 'domains'):
                    current_count += len(app.domains)
            
            limit = plan.max_domains
            if limit == -1:  # Unlimited
                return {'allowed': True, 'current': current_count, 'limit': 'unlimited'}
            return {
                'allowed': current_count < limit,
                'current': current_count,
                'limit': limit,
                'remaining': max(0, limit - current_count)
            }
        
        elif resource == 'api_calls':
            # Get current API usage from subscription-level tracking
            current_count = SubscriptionService.get_current_api_usage(user_id)
            
            limit = plan.max_api_calls_per_month
            if limit == -1:  # Unlimited
                return {'allowed': True, 'current': current_count, 'limit': 'unlimited'}
            return {
                'allowed': current_count < limit,
                'current': current_count,
                'limit': limit,
                'remaining': max(0, limit - current_count)
            }
        
        return {'allowed': True}
    
    @staticmethod
    def get_current_api_usage(user_id: int) -> int:
        """Get current month's API usage for a user"""
        from model.api_usage import APIUsage
        from datetime import datetime
        
        user = db.session.query(User).get(user_id)
        if not user or not user.subscription:
            return 0
        
        current_subscription = user.subscription
        if not current_subscription:
            return 0
        
        now = datetime.utcnow()
        current_year = now.year
        current_month = now.month
        
        usage_record = db.session.query(APIUsage).filter_by(
            user_id=user_id,
            subscription_id=current_subscription.subscription_id,
            year=current_year,
            month=current_month
        ).first()
        
        return usage_record.api_calls_count if usage_record else 0
    
    @staticmethod
    def get_all_plans() -> List[Plan]:
        """Get all available plans"""
        return db.session.query(Plan).filter_by(is_active=True).all()
    
    @staticmethod
    def get_user_subscription_info(user_id: int) -> dict:
        """Get comprehensive subscription information for a user"""
        user = db.session.query(User).get(user_id)
        if not user:
            return None
        
        subscription = user.subscription
        plan = user.current_plan
        
        return {
            'plan': {
                'name': plan.name,
                'display_name': plan.display_name,
                'price': float(plan.price),
                'features': {
                    'max_agents': plan.max_agents,
                    'max_storage_gb': plan.max_storage_gb,
                    'max_domains': plan.max_domains,
                    'max_api_calls_per_month': plan.max_api_calls_per_month,
                    'has_priority_support': plan.has_priority_support,
                    'has_advanced_analytics': plan.has_advanced_analytics,
                    'has_team_collaboration': plan.has_team_collaboration,
                    'has_custom_integrations': plan.has_custom_integrations,
                    'has_on_premise': plan.has_on_premise
                }
            },
            'subscription': {
                'status': subscription.status.value if subscription else 'none',
                'is_trial': subscription.is_trial if subscription else False,
                'trial_ends_at': subscription.trial_ends_at.isoformat() if subscription and subscription.trial_ends_at else None,
                'expires_at': subscription.expires_at.isoformat() if subscription and subscription.expires_at else None,
                'days_until_expiry': subscription.days_until_expiry if subscription else None
            },
            'usage': {
                'agents': SubscriptionService.check_usage_limits(user_id, 'agents'),
                'domains': SubscriptionService.check_usage_limits(user_id, 'domains'),
                'api_calls': SubscriptionService.check_usage_limits(user_id, 'api_calls')
            }
        } 