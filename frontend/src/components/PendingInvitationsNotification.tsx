import { useState, useEffect } from 'react';
import { CheckCircle2, AlertTriangle, X } from 'lucide-react';
import { apiService } from '../services/api';
import ButtonApp from './ui/ButtonApp';
import { useTranslation } from 'react-i18next';

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
  const { t, i18n } = useTranslation('common');
  const [invitations, setInvitations] = useState<PendingInvitation[]>([]);
  const [loading, setLoading] = useState(false);
  const [showDetails, setShowDetails] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  useEffect(() => {
    void loadPendingInvitations();
  }, []);

  async function loadPendingInvitations() {
    try {
      const response = await apiService.getPendingInvitations();
      setInvitations(response);
    } catch (error) {
      console.error('Failed to load pending invitations:', error);
    }
  }

  const toggleDetails = () => {
    const newShowDetails = !showDetails;
    setShowDetails(newShowDetails);
    
    if (newShowDetails) {
      void loadPendingInvitations();
    }
  };

  async function handleInvitationResponse(invitationId: number, action: 'accept' | 'decline') {
    try {
      setLoading(true);
      setMessage(null);
      await apiService.respondToInvitation(invitationId, action);
      
      setInvitations(prev => prev.filter(inv => inv.id !== invitationId));
      setMessage({
        type: 'success',
        text: t(`collaborationPage.pendingInvitations.${action}Success`),
      });
      setTimeout(() => setMessage(null), 3000);
      
    } catch (error) {
      console.error(`Failed to ${action} invitation:`, error);
      setMessage({
        type: 'error',
        text: t(`collaborationPage.pendingInvitations.${action}Failed`),
      });
    } finally {
      setLoading(false);
    }
  }

  if (invitations.length === 0) {
    return null;
  }

  return (
    <div className="relative">
      <button
        onClick={toggleDetails}
        className="relative w-[34px] h-[34px] flex items-center justify-center text-fg-secondary hover:bg-surface-hover transition-colors rounded-lg focus:outline-none focus-visible:ring-2 focus-visible:ring-focus dark:text-fg-secondary-dark dark:hover:bg-surface-hover-dark dark:focus-visible:ring-focus-dark"
        title={t('collaborationPage.pendingInvitations.count', { count: invitations.length })}
        aria-label={t('collaborationPage.pendingInvitations.count', { count: invitations.length })}
      >
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 17h5l-3.5-3.5a2.5 2.5 0 010-3.5L19 7h-5M9 17H4l3.5-3.5a2.5 2.5 0 000-3.5L4 7h5m0 0V4a2 2 0 112 4h2a2 2 0 112 4v3" />
        </svg>
        
        <span className="absolute top-0.5 right-0.5 bg-accent text-white text-[10px] font-medium rounded-full h-4 min-w-4 px-1 flex items-center justify-center dark:bg-accent-dark dark:text-ink-on-dark">
          {invitations.length}
        </span>
      </button>

      {showDetails && (
        <>
          <button
            type="button"
            aria-label={t('collaborationPage.pendingInvitations.closePanel')}
            className="fixed inset-0 z-10 cursor-default bg-transparent border-0 p-0 w-full h-full"
            onClick={() => setShowDetails(false)}
            onKeyDown={(e) => { if (e.key === 'Escape') setShowDetails(false); }}
          />
          
          <div className="absolute top-full right-0 mt-2 w-80 bg-surface border border-line rounded-lg shadow-[0_14px_40px_rgba(32,28,20,0.14)] overflow-visible  dark:bg-surface-dark dark:border-line-dark dark:shadow-[0_14px_40px_rgba(0,0,0,0.55)] z-20">
            <div className="p-3 border-b border-line dark:border-line-dark">
              <h3 className="text-sm  text-fg dark:text-fg-dark">
                {t('collaborationPage.pendingInvitations.title', { count: invitations.length })}
              </h3>
            </div>
            
            {message && (
              <div className={`p-3 border-b border-line dark:border-line-dark ${
                message.type === 'success' ? 'bg-green-50' : 'bg-red-50'
              }`}>
                <div className="flex items-center">
                  <span className={`text-sm mr-2 ${
                    message.type === 'success' ? 'text-green-600' : 'text-red-600'
                  }`}>
                    {message.type === 'success' ? <CheckCircle2 className="w-4 h-4" /> : <AlertTriangle className="w-4 h-4" />}
                  </span>
                  <p className={`text-xs ${
                    message.type === 'success' ? 'text-green-800' : 'text-red-800'
                  }`}>
                    {message.text}
                  </p>
                  <button
                    onClick={() => setMessage(null)}
                    aria-label={t('collaborationPage.pendingInvitations.dismissMessage')}
                    className={`ml-auto text-xs ${
                      message.type === 'success' ? 'text-green-600 hover:text-green-800' : 'text-red-600 hover:text-red-800'
                    }`}
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>
              </div>
            )}
            
            <div className="max-h-60 overflow-y-auto">
              {invitations.map((invitation) => (
                <div key={invitation.id} className="p-3 border-b border-line dark:border-line-dark last:border-b-0">
                  <div className="space-y-2">
                    {/* Ownership offers (role=owner) render differently from normal collaboration invites */}
                    <div>
                      <div className="flex items-center gap-2 flex-wrap">
                        <h4 className="font-medium text-fg dark:text-fg-dark text-sm">{invitation.app_name}</h4>
                        {invitation.role.toLowerCase() === 'owner' && (
                          <span className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200">
                            {t('collaborationPage.pendingInvitations.ownershipTransfer')}
                          </span>
                        )}
                      </div>
                      {invitation.role.toLowerCase() === 'owner' ? (
                        <p className="text-xs text-fg-secondary dark:text-fg-secondary-dark">
                          {t('collaborationPage.pendingInvitations.transferOwnershipMessage', {
                            inviter: invitation.inviter_name || invitation.inviter_email,
                          })}
                        </p>
                      ) : (
                        <p className="text-xs text-fg-secondary dark:text-fg-secondary-dark">
                          {t('collaborationPage.pendingInvitations.invitedAs', {
                            inviter: invitation.inviter_name || invitation.inviter_email,
                            role: t(`collaborationPage.roles.${invitation.role.toLowerCase()}`, {
                              defaultValue: invitation.role,
                            }),
                          })}
                        </p>
                      )}
                      <p className="text-xs text-fg-secondary dark:text-fg-secondary-dark mt-1">
                        {new Date(invitation.invited_at).toLocaleDateString(
                          i18n.resolvedLanguage ?? i18n.language,
                        )}
                      </p>
                    </div>

                    <div className="flex space-x-2">
                      <ButtonApp
                        label={t('collaborationPage.pendingInvitations.accept')}
                        type="button"
                        onClick={() => handleInvitationResponse(invitation.id, 'accept')}
                        disabled={loading}
                        variant="primary"
                        size="small"
                        className="flex-1"
                      />
                      <ButtonApp
                        label={t('collaborationPage.pendingInvitations.decline')}
                        type="button"
                        onClick={() => handleInvitationResponse(invitation.id, 'decline')}
                        disabled={loading}
                        variant="secondary"
                        size="small"
                        className="flex-1"
                      />
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