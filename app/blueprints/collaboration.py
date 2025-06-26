from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from services.app_service import AppService
from services.app_collaboration_service import AppCollaborationService
from model.app_collaborator import CollaborationRole
import logging

logger = logging.getLogger(__name__)
collaboration_blueprint = Blueprint('collaboration', __name__)

@collaboration_blueprint.route('/app/<int:app_id>/collaboration')
@login_required
def collaboration(app_id):
    """View app collaboration settings"""
    app = AppService.get_app(app_id)
    if not app:
        flash('App not found', 'error')
        return redirect(url_for('home'))
    
    # Set session variables for the template (needed by app_settings_base.html)
    from flask import session
    session['app_id'] = app_id
    session['app_name'] = app.name
    
    # Check if user has permission to manage collaborations
    try:
        user_id = int(current_user.user_id) if current_user.user_id else None
        if user_id is None:
            logger.error(f"User ID is None for current_user: {current_user}")
            flash('User ID not found', 'error')
            return redirect(url_for('home'))
        
        logger.info(f"Checking user role for user_id: {user_id}, app_id: {app_id}")
        user_role = app.get_user_role(user_id)
        logger.info(f"User role determined: {user_role}")
        
        if user_role != CollaborationRole.OWNER:
            flash('You do not have permission to manage collaborations for this app', 'error')
            return redirect(url_for('app_index', app_id=app_id))
    except (ValueError, AttributeError) as e:
        logger.error(f"Error checking user permissions: {str(e)}")
        logger.error(f"current_user: {current_user}")
        logger.error(f"current_user.user_id: {getattr(current_user, 'user_id', 'NO_USER_ID_ATTR')}")
        logger.error(f"current_user type: {type(current_user)}")
        flash('Error checking user permissions', 'error')
        return redirect(url_for('home'))
    
    return render_template('collaboration/collaboration.html', app=app)

# API routes for collaboration management
@collaboration_blueprint.route('/apps/<int:app_id>/collaborators', methods=['GET'])
@login_required
def get_app_collaborators(app_id):
    """Get all collaborators for an app"""
    try:
        # Check if user has access to this app
        user_id = int(current_user.user_id)
        if not AppCollaborationService.can_user_access_app(user_id, app_id):
            return jsonify({"error": "Unauthorized"}), 401
        
        # Get all collaborators (accepted, pending, declined)
        collaborators = AppCollaborationService.get_app_collaborators(app_id)
        
        # Format response
        collaborators_data = []
        for collab in collaborators:
            collaborator_data = {
                'id': collab.id,
                'user_id': collab.user_id,
                'user_email': collab.user.email if collab.user else None,
                'user_name': collab.user.name if collab.user else None,
                'role': collab.role.value,
                'status': collab.status.value,
                'invited_by': collab.invited_by,
                'inviter_email': collab.inviter.email if collab.inviter else None,
                'invited_at': collab.invited_at.isoformat() if collab.invited_at else None,
                'accepted_at': collab.accepted_at.isoformat() if collab.accepted_at else None
            }
            collaborators_data.append(collaborator_data)
        
        return jsonify({
            'success': True,
            'collaborators': collaborators_data
        })
        
    except Exception as e:
        logger.error(f"Error getting collaborators for app {app_id}: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Failed to get collaborators'
        }), 500

@collaboration_blueprint.route('/apps/<int:app_id>/collaborators', methods=['POST'])
@login_required
def invite_collaborator(app_id):
    """Invite a user to collaborate on an app"""
    try:
        # Check if user is the owner
        user_id = int(current_user.user_id)
        if not AppCollaborationService.can_user_manage_app(user_id, app_id):
            return jsonify({"error": "Unauthorized - Owner access required"}), 403
        
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'error': 'No data provided'
            }), 400
        
        user_email = data.get('email')
        role_str = data.get('role', 'editor')
        
        if not user_email:
            return jsonify({
                'success': False,
                'error': 'Email is required'
            }), 400
        
        # Convert role string to enum
        try:
            role = CollaborationRole(role_str.lower())
        except ValueError:
            return jsonify({
                'success': False,
                'error': 'Invalid role. Must be "owner" or "editor"'
            }), 400
        
        # Invite the user
        collaboration = AppCollaborationService.invite_user_to_app(
            app_id=app_id,
            user_email=user_email,
            invited_by_user_id=user_id,
            role=role
        )
        
        if collaboration:
            return jsonify({
                'success': True,
                'message': f'Invitation sent to {user_email}',
                'collaboration': {
                    'id': collaboration.id,
                    'user_email': user_email,
                    'role': collaboration.role.value,
                    'status': collaboration.status.value
                }
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to send invitation'
            }), 500
            
    except Exception as e:
        logger.error(f"Error inviting collaborator to app {app_id}: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

@collaboration_blueprint.route('/apps/<int:app_id>/collaborators/<int:user_id>', methods=['DELETE'])
@login_required
def revoke_collaboration(app_id, user_id):
    """Revoke a user's collaboration on an app"""
    try:
        # Check if user is the owner
        current_user_id = int(current_user.user_id)
        if not AppCollaborationService.can_user_manage_app(current_user_id, app_id):
            return jsonify({"error": "Unauthorized - Owner access required"}), 403
        
        success = AppCollaborationService.revoke_collaboration(
            app_id=app_id,
            user_id=user_id,
            revoked_by_user_id=current_user_id
        )
        
        if success:
            return jsonify({
                'success': True,
                'message': 'Collaboration revoked successfully'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to revoke collaboration'
            }), 500
            
    except Exception as e:
        logger.error(f"Error revoking collaboration for app {app_id}, user {user_id}: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

@collaboration_blueprint.route('/collaborations/<int:collaboration_id>/accept', methods=['POST'])
@login_required
def accept_invitation(collaboration_id):
    """Accept a collaboration invitation"""
    try:
        user_id = int(current_user.user_id)
        collaboration = AppCollaborationService.accept_invitation(
            collaboration_id=collaboration_id,
            user_id=user_id
        )
        
        if collaboration:
            return jsonify({
                'success': True,
                'message': 'Invitation accepted successfully',
                'collaboration': {
                    'id': collaboration.id,
                    'app_id': collaboration.app_id,
                    'role': collaboration.role.value,
                    'status': collaboration.status.value
                }
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to accept invitation'
            }), 500
            
    except Exception as e:
        logger.error(f"Error accepting invitation {collaboration_id}: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

@collaboration_blueprint.route('/collaborations/<int:collaboration_id>/decline', methods=['POST'])
@login_required
def decline_invitation(collaboration_id):
    """Decline a collaboration invitation"""
    try:
        user_id = int(current_user.user_id)
        success = AppCollaborationService.decline_invitation(
            collaboration_id=collaboration_id,
            user_id=user_id
        )
        
        if success:
            return jsonify({
                'success': True,
                'message': 'Invitation declined successfully'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to decline invitation'
            }), 500
            
    except Exception as e:
        logger.error(f"Error declining invitation {collaboration_id}: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

@collaboration_blueprint.route('/apps/<int:app_id>/leave', methods=['POST'])
@login_required
def leave_app(app_id):
    """Leave an app (for collaborators only)"""
    try:
        user_id = int(current_user.user_id)
        
        success = AppCollaborationService.leave_app(
            app_id=app_id,
            user_id=user_id
        )
        
        if success:
            return jsonify({
                'success': True,
                'message': 'Successfully left the app'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to leave the app'
            }), 500
            
    except Exception as e:
        logger.error(f"Error leaving app {app_id}: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400 