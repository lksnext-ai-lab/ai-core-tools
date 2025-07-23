import { useState, useEffect } from 'react';
import { apiService } from '../services/api';

interface PendingInvitation {
  id: number;
  app_id: number;
  app_name: string;
  inviter_email: string;
  inviter_name?: string;
  invited_at: string;
  role: string;
}

function PendingInvitationsNotification() {
  const [invitations, setInvitations] = useState<PendingInvitation[]>([]);
  const [loading, setLoading] = useState(false);
  const [showDetails, setShowDetails] = useState(false);

  useEffect(() => {
    loadPendingInvitations();
  }, []);

  async function loadPendingInvitations() {
    try {
      const response = await apiService.getPendingInvitations();
      setInvitations(response);
    } catch (error) {
      console.error('Failed to load pending invitations:', error);
    }
  }

  async function handleInvitationResponse(invitationId: number, action: 'accept' | 'decline') {
    try {
      setLoading(true);
      await apiService.respondToInvitation(invitationId, action);
      
      // Remove the invitation from the list
      setInvitations(prev => prev.filter(inv => inv.id !== invitationId));
      
      // Show success message
      const actionText = action === 'accept' ? 'accepted' : 'declined';
      alert(`Invitation ${actionText} successfully!`);
      
    } catch (error) {
      alert(`Failed to ${action} invitation`);
    } finally {
      setLoading(false);
    }
  }

  if (invitations.length === 0) {
    return null;
  }

  return (
    <div className="relative">
      {/* Notification Bell */}
      <button
        onClick={() => setShowDetails(!showDetails)}
        className="relative p-1.5 text-gray-400 hover:text-gray-600 transition-colors rounded-md hover:bg-gray-100"
        title={`${invitations.length} pending invitation${invitations.length !== 1 ? 's' : ''}`}
      >
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 17h5l-3.5-3.5a2.5 2.5 0 010-3.5L19 7h-5M9 17H4l3.5-3.5a2.5 2.5 0 000-3.5L4 7h5m0 0V4a2 2 0 112 4h2a2 2 0 112 4v3" />
        </svg>
        
        {/* Badge */}
        <span className="absolute -top-1 -right-1 bg-red-500 text-white text-xs rounded-full h-4 w-4 flex items-center justify-center">
          {invitations.length}
        </span>
      </button>

      {/* Dropdown */}
      {showDetails && (
        <>
          {/* Backdrop */}
          <div 
            className="fixed inset-0 z-10" 
            onClick={() => setShowDetails(false)}
          />
          
          {/* Notification Panel - positioned below the button */}
          <div className="absolute top-full right-0 mt-2 w-80 bg-white rounded-lg shadow-lg border border-gray-200 z-20">
            <div className="p-3 border-b border-gray-200">
              <h3 className="text-sm font-semibold text-gray-900">
                Pending Invitations ({invitations.length})
              </h3>
            </div>
            
            <div className="max-h-60 overflow-y-auto">
              {invitations.map((invitation) => (
                <div key={invitation.id} className="p-3 border-b border-gray-100 last:border-b-0">
                  <div className="space-y-2">
                    {/* Invitation Info */}
                    <div>
                      <h4 className="font-medium text-gray-900 text-sm">{invitation.app_name}</h4>
                      <p className="text-xs text-gray-600">
                        {invitation.inviter_name || invitation.inviter_email} invited you as an{' '}
                        <span className="font-medium">{invitation.role}</span>
                      </p>
                      <p className="text-xs text-gray-500 mt-1">
                        {new Date(invitation.invited_at).toLocaleDateString()}
                      </p>
                    </div>

                    {/* Action Buttons */}
                    <div className="flex space-x-2">
                      <button
                        onClick={() => handleInvitationResponse(invitation.id, 'accept')}
                        disabled={loading}
                        className="flex-1 px-2 py-1 bg-green-600 hover:bg-green-700 text-white text-xs rounded transition-colors disabled:opacity-50"
                      >
                        Accept
                      </button>
                      <button
                        onClick={() => handleInvitationResponse(invitation.id, 'decline')}
                        disabled={loading}
                        className="flex-1 px-2 py-1 bg-gray-600 hover:bg-gray-700 text-white text-xs rounded transition-colors disabled:opacity-50"
                      >
                        Decline
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

export default PendingInvitationsNotification; 