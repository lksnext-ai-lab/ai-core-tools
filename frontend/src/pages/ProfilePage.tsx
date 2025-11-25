import React, { useState, useEffect } from 'react';
import { useUser } from '../contexts/UserContext';
import { apiService } from '../services/api';
import Alert from '../components/ui/Alert';

interface App {
  app_id: number;
  name: string;
  role: string;
  owner_name?: string;
  owner_email?: string;
}

interface PendingInvitation {
  id: number;
  app_id: number;
  app_name: string;
  inviter_email: string;
  role: string;
  invited_at: string;
}

const ProfilePage: React.FC = () => {
  const { user, loading: userLoading } = useUser();
  const [collaborations, setCollaborations] = useState<App[]>([]);
  const [invitations, setInvitations] = useState<PendingInvitation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  useEffect(() => {
    if (user) {
      loadData();
    }
  }, [user]);

  async function loadData() {
    try {
      setLoading(true);
      const [appsData, invitationsData] = await Promise.all([
        apiService.getApps(),
        apiService.getPendingInvitations()
      ]);

      // Filter apps where user is not owner
      const collabs = appsData.filter((app: any) => app.role !== 'owner');
      setCollaborations(collabs);
      setInvitations(invitationsData);
    } catch (err) {
      console.error(err);
      // Don't show error if it's just empty data or minor issue
    } finally {
      setLoading(false);
    }
  }

  async function handleRespond(invitationId: number, action: 'accept' | 'decline') {
    try {
      await apiService.respondToInvitation(invitationId, action);
      setSuccess(`Invitation ${action}ed successfully`);
      loadData();
      setTimeout(() => setSuccess(null), 3000);
    } catch (err) {
      console.error(err);
      setError(`Failed to ${action} invitation`);
      setTimeout(() => setError(null), 3000);
    }
  }

  async function handleLeaveApp(appId: number, appName: string) {
    if (!globalThis.confirm(`Are you sure you want to leave "${appName}"?`)) {
      return;
    }
    try {
      await apiService.leaveApp(appId);
      setSuccess(`Left app "${appName}" successfully`);
      loadData();
      setTimeout(() => setSuccess(null), 3000);
    } catch (err) {
      console.error(err);
      setError('Failed to leave app');
      setTimeout(() => setError(null), 3000);
    }
  }

  const getUserInitials = (name?: string, email?: string) => {
    if (name) {
      return name.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2);
    }
    if (email) {
      return email[0].toUpperCase().slice(0, 2);
    }
    return 'U';
  };

  const getRoleBadgeClass = (role: string) => {
    switch (role) {
      case 'administrator':
        return 'bg-purple-100 text-purple-800';
      case 'editor':
        return 'bg-blue-100 text-blue-800';
      default:
        return 'bg-gray-100 text-gray-800';
    }
  };

  if (userLoading) {
    return (
      <div className="flex justify-center items-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600"></div>
      </div>
    );
  }

  if (!user) {
    return (
      <div className="p-6">
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded relative" role="alert">
          <strong className="font-bold">Error: </strong>
          <span className="block sm:inline">User not found. Please log in.</span>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-5xl mx-auto py-8 px-4 sm:px-6 lg:px-8 space-y-8">
      {success && <Alert type="success" message={success} onDismiss={() => setSuccess(null)} />}
      {error && <Alert type="error" message={error} onDismiss={() => setError(null)} />}

      {/* Profile Header */}
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
        <div className="h-32 bg-gradient-to-r from-indigo-500 to-purple-600"></div>
        <div className="px-6 pb-6">
          <div className="relative flex items-end -mt-6 mb-4">
            <div className="h-24 w-24 rounded-2xl bg-white p-1 shadow-lg">
              <div className="h-full w-full rounded-xl bg-indigo-100 flex items-center justify-center text-2xl font-bold text-indigo-600">
                {getUserInitials(user.name, user.email)}
              </div>
            </div>
            <div className="ml-4 mb-1">
              <h1 className="text-2xl font-bold text-gray-900">{user.name || 'User'}</h1>
              <p className="text-sm text-gray-500">{user.email}</p>
            </div>
          </div>
          
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 border-t border-gray-100 pt-6">
            <div className="text-center">
              <dt className="text-xs font-medium text-gray-500 uppercase tracking-wider">User ID</dt>
              <dd className="mt-1 text-sm font-semibold text-gray-900">#{user.user_id}</dd>
            </div>
            <div className="text-center">
              <dt className="text-xs font-medium text-gray-500 uppercase tracking-wider">Account Type</dt>
              <dd className="mt-1 text-sm font-semibold text-gray-900">Standard User</dd>
            </div>
            <div className="text-center">
              <dt className="text-xs font-medium text-gray-500 uppercase tracking-wider">Status</dt>
              <dd className="mt-1 text-sm font-semibold text-green-600 flex items-center justify-center">
                <span className="h-2 w-2 bg-green-500 rounded-full mr-2"></span>Active
              </dd>
            </div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        {/* Pending Invitations */}
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold text-gray-900 flex items-center">
              <span className="bg-yellow-100 text-yellow-600 p-2 rounded-lg mr-3">📩</span>Pending Invitations
            </h2>
            {invitations.length > 0 && (
              <span className="bg-yellow-100 text-yellow-800 text-xs font-medium px-2.5 py-0.5 rounded-full">
                {invitations.length}
              </span>
            )}
          </div>
          
          <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
            {loading && (
              <div className="p-8 text-center">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600 mx-auto"></div>
                <p className="mt-2 text-sm text-gray-500">Loading invitations...</p>
              </div>
            )}
            {!loading && invitations.length > 0 && (
              <ul className="divide-y divide-gray-100">
                {invitations.map((invitation) => (
                  <li key={invitation.id} className="p-4 hover:bg-gray-50 transition-colors">
                    <div className="flex flex-col space-y-3">
                      <div className="flex justify-between items-start">
                        <div>
                          <h4 className="text-sm font-semibold text-gray-900">{invitation.app_name}</h4>
                          <p className="text-xs text-gray-500 mt-1">
                            Invited by <span className="font-medium text-gray-700">{invitation.inviter_email}</span>
                          </p>
                        </div>
                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-indigo-100 text-indigo-800 capitalize">
                          {invitation.role}
                        </span>
                      </div>
                      
                      <div className="flex items-center justify-between pt-2">
                        <span className="text-xs text-gray-400">
                          {new Date(invitation.invited_at).toLocaleDateString()}
                        </span>
                        <div className="flex space-x-2">
                          <button
                            onClick={() => handleRespond(invitation.id, 'decline')}
                            className="px-3 py-1.5 text-xs font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 transition-colors"
                          >
                            Decline
                          </button>
                          <button
                            onClick={() => handleRespond(invitation.id, 'accept')}
                            className="px-3 py-1.5 text-xs font-medium text-white bg-indigo-600 border border-transparent rounded-lg hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 transition-colors shadow-sm"
                          >
                            Accept
                          </button>
                        </div>
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            )}
            {!loading && invitations.length === 0 && (
              <div className="p-8 text-center">
                <div className="mx-auto h-12 w-12 text-gray-300 mb-3">
                  <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4" />
                  </svg>
                </div>
                <p className="text-sm text-gray-500">No pending invitations</p>
              </div>
            )}
          </div>
        </div>

        {/* Active Collaborations */}
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold text-gray-900 flex items-center">
              <span className="bg-blue-100 text-blue-600 p-2 rounded-lg mr-3">🤝</span>Active Collaborations
            </h2>
            {collaborations.length > 0 && (
              <span className="bg-blue-100 text-blue-800 text-xs font-medium px-2.5 py-0.5 rounded-full">
                {collaborations.length}
              </span>
            )}
          </div>

          <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
            {loading && (
              <div className="p-8 text-center">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto"></div>
                <p className="mt-2 text-sm text-gray-500">Loading collaborations...</p>
              </div>
            )}
            {!loading && collaborations.length > 0 && (
              <ul className="divide-y divide-gray-100">
                {collaborations.map((app) => (
                  <li key={app.app_id} className="p-4 hover:bg-gray-50 transition-colors">
                    <div className="flex items-center justify-between">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center space-x-2">
                          <h4 className="text-sm font-semibold text-gray-900 truncate">{app.name}</h4>
                          <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium capitalize ${getRoleBadgeClass(app.role)}`}>
                            {app.role}
                          </span>
                        </div>
                        <p className="mt-1 text-xs text-gray-500 flex items-center">
                          <span className="mr-1">👑</span>
                          {app.owner_name || app.owner_email || 'Unknown'}
                        </p>
                      </div>
                      <button
                        onClick={() => handleLeaveApp(app.app_id, app.name)}
                        className="ml-4 p-2 text-gray-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                        title="Leave App"
                      >
                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
                        </svg>
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
            {!loading && collaborations.length === 0 && (
              <div className="p-8 text-center">
                <div className="mx-auto h-12 w-12 text-gray-300 mb-3">
                  <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" />
                  </svg>
                </div>
                <p className="text-sm text-gray-500">No active collaborations</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default ProfilePage;
