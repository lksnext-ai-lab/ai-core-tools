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
    if (!window.confirm(`Are you sure you want to leave "${appName}"?`)) {
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
    <div className="max-w-4xl mx-auto py-8 px-4 sm:px-6 lg:px-8 space-y-8">
      {success && <Alert type="success" message={success} onDismiss={() => setSuccess(null)} />}
      {error && <Alert type="error" message={error} onDismiss={() => setError(null)} />}

      {/* User Profile Section */}
      <div className="bg-white shadow overflow-hidden sm:rounded-lg">
        <div className="px-4 py-5 sm:px-6">
          <h3 className="text-lg leading-6 font-medium text-gray-900">User Profile</h3>
          <p className="mt-1 max-w-2xl text-sm text-gray-500">Personal details and application information.</p>
        </div>
        <div className="border-t border-gray-200">
          <dl>
            <div className="bg-gray-50 px-4 py-5 sm:grid sm:grid-cols-3 sm:gap-4 sm:px-6">
              <dt className="text-sm font-medium text-gray-500">Full name</dt>
              <dd className="mt-1 text-sm text-gray-900 sm:mt-0 sm:col-span-2">{user.name || 'N/A'}</dd>
            </div>
            <div className="bg-white px-4 py-5 sm:grid sm:grid-cols-3 sm:gap-4 sm:px-6">
              <dt className="text-sm font-medium text-gray-500">Email address</dt>
              <dd className="mt-1 text-sm text-gray-900 sm:mt-0 sm:col-span-2">{user.email}</dd>
            </div>
            <div className="bg-gray-50 px-4 py-5 sm:grid sm:grid-cols-3 sm:gap-4 sm:px-6">
              <dt className="text-sm font-medium text-gray-500">User ID</dt>
              <dd className="mt-1 text-sm text-gray-900 sm:mt-0 sm:col-span-2">{user.user_id}</dd>
            </div>
          </dl>
        </div>
      </div>

      {/* Pending Invitations Section */}
      {invitations.length > 0 && (
        <div className="bg-white shadow overflow-hidden sm:rounded-lg">
          <div className="px-4 py-5 sm:px-6 border-b border-gray-200">
            <h3 className="text-lg leading-6 font-medium text-gray-900 flex items-center">
              <span className="mr-2">📩</span> Pending Invitations
            </h3>
            <p className="mt-1 max-w-2xl text-sm text-gray-500">Apps you have been invited to join.</p>
          </div>
          <ul className="divide-y divide-gray-200">
            {invitations.map((invitation) => (
              <li key={invitation.id} className="px-4 py-4 sm:px-6 hover:bg-gray-50">
                <div className="flex items-center justify-between">
                  <div className="flex-1 min-w-0">
                    <h4 className="text-sm font-medium text-indigo-600 truncate">{invitation.app_name}</h4>
                    <p className="mt-1 text-sm text-gray-500">
                      Invited by <span className="font-medium">{invitation.inviter_email}</span> as <span className="font-medium capitalize">{invitation.role}</span>
                    </p>
                    <p className="mt-1 text-xs text-gray-400">
                      {new Date(invitation.invited_at).toLocaleDateString()}
                    </p>
                  </div>
                  <div className="flex space-x-3 ml-4">
                    <button
                      onClick={() => handleRespond(invitation.id, 'accept')}
                      className="inline-flex items-center px-3 py-1.5 border border-transparent text-xs font-medium rounded-md text-white bg-green-600 hover:bg-green-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-green-500"
                    >
                      Accept
                    </button>
                    <button
                      onClick={() => handleRespond(invitation.id, 'decline')}
                      className="inline-flex items-center px-3 py-1.5 border border-gray-300 text-xs font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500"
                    >
                      Decline
                    </button>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Active Collaborations Section */}
      <div className="bg-white shadow overflow-hidden sm:rounded-lg">
        <div className="px-4 py-5 sm:px-6 border-b border-gray-200">
          <h3 className="text-lg leading-6 font-medium text-gray-900 flex items-center">
            <span className="mr-2">🤝</span> Active Collaborations
          </h3>
          <p className="mt-1 max-w-2xl text-sm text-gray-500">Apps you are collaborating on.</p>
        </div>
        {collaborations.length > 0 ? (
          <ul className="divide-y divide-gray-200">
            {collaborations.map((app) => (
              <li key={app.app_id} className="px-4 py-4 sm:px-6 hover:bg-gray-50">
                <div className="flex items-center justify-between">
                  <div className="flex-1 min-w-0">
                    <h4 className="text-sm font-medium text-indigo-600 truncate">{app.name}</h4>
                    <p className="mt-1 text-sm text-gray-500">
                      Role: <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-blue-100 text-blue-800 capitalize">
                        {app.role}
                      </span>
                    </p>
                    <p className="mt-1 text-xs text-gray-400">
                      Owner: {app.owner_name || app.owner_email || 'Unknown'}
                    </p>
                  </div>
                  <div className="ml-4">
                    <button
                      onClick={() => handleLeaveApp(app.app_id, app.name)}
                      className="inline-flex items-center px-3 py-1.5 border border-transparent text-xs font-medium rounded-md text-red-700 bg-red-100 hover:bg-red-200 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-red-500"
                    >
                      Leave App
                    </button>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <div className="px-4 py-5 sm:px-6 text-center text-gray-500 text-sm">
            You are not collaborating on any apps yet.
          </div>
        )}
      </div>
    </div>
  );
};

export default ProfilePage;
