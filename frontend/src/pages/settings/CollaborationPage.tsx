import { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import SettingsLayout from '../../components/layout/SettingsLayout';
import CollaborationForm from '../../components/forms/CollaborationForm';
import { apiService } from '../../services/api';
import { useUser } from '../../contexts/UserContext';

interface Collaborator {
  id: number;
  user_id: number;
  user_email: string;
  user_name?: string;
  role: string;
  status: string;
  invited_at: string;
  accepted_at?: string;
  invited_by_name?: string;
}

function CollaborationPage() {
  const { appId } = useParams();
  const { user } = useUser();
  const [collaborators, setCollaborators] = useState<Collaborator[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [currentUserRole, setCurrentUserRole] = useState<string | null>(null);

  // Load collaborators from the API
  useEffect(() => {
    loadCollaborators();
    checkUserRole();
  }, [appId]);

  async function loadCollaborators() {
    if (!appId) return;
    
    try {
      setLoading(true);
      setError(null);
      const response = await apiService.getCollaborators(parseInt(appId));
      setCollaborators(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load collaborators');
      console.error('Error loading collaborators:', err);
    } finally {
      setLoading(false);
    }
  }

  async function checkUserRole() {
    if (!appId) return;
    
    try {
      // Get app details to check if current user is owner
      const app = await apiService.getApp(parseInt(appId));
      if (app.owner_id === user?.user_id) {
        setCurrentUserRole('owner');
      } else {
        setCurrentUserRole('editor');
      }
    } catch (err) {
      console.error('Error checking user role:', err);
      setCurrentUserRole('editor'); // Default to editor if we can't determine
    }
  }

  async function handleInviteUser(email: string, role: string) {
    if (!appId) return;

    try {
      await apiService.inviteCollaborator(parseInt(appId), email, role);
      // Reload collaborators list
      await loadCollaborators();
    } catch (err) {
      throw new Error(err instanceof Error ? err.message : 'Failed to send invitation');
    }
  }

  async function handleUpdateRole(userId: number, newRole: string) {
    if (!appId) return;

    try {
      await apiService.updateCollaboratorRole(parseInt(appId), userId, newRole);
      // Reload collaborators list
      await loadCollaborators();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update role');
      console.error('Error updating role:', err);
    }
  }

  async function handleRemoveCollaborator(userId: number) {
    if (!confirm('Are you sure you want to remove this collaborator? They will lose access to this app.')) {
      return;
    }

    if (!appId) return;

    try {
      await apiService.removeCollaborator(parseInt(appId), userId);
      // Remove from local state
      setCollaborators(collaborators.filter(c => c.user_id !== userId));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to remove collaborator');
      console.error('Error removing collaborator:', err);
    }
  }

  const getStatusBadge = (status: string) => {
    switch (status.toLowerCase()) {
      case 'accepted':
        return 'bg-green-100 text-green-800';
      case 'pending':
        return 'bg-yellow-100 text-yellow-800';
      case 'declined':
        return 'bg-red-100 text-red-800';
      default:
        return 'bg-gray-100 text-gray-800';
    }
  };

  const getRoleBadge = (role: string) => {
    switch (role.toLowerCase()) {
      case 'owner':
        return 'bg-purple-100 text-purple-800';
      case 'editor':
        return 'bg-blue-100 text-blue-800';
      default:
        return 'bg-gray-100 text-gray-800';
    }
  };

  const isOwner = currentUserRole === 'owner';

  if (loading) {
    return (
      <SettingsLayout>
        <div className="p-6 text-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600 mx-auto"></div>
          <p className="mt-2 text-gray-600">Loading collaboration settings...</p>
        </div>
      </SettingsLayout>
    );
  }

  if (error) {
    return (
      <SettingsLayout>
        <div className="p-6">
          <div className="bg-red-50 border border-red-200 rounded-lg p-4">
            <p className="text-red-600">Error: {error}</p>
            <button 
              onClick={() => loadCollaborators()}
              className="mt-2 text-red-800 hover:text-red-900 underline"
            >
              Try again
            </button>
          </div>
        </div>
      </SettingsLayout>
    );
  }

  return (
    <SettingsLayout>
      <div className="p-6 space-y-8">
        {/* Header */}
        <div>
          <h2 className="text-xl font-semibold text-gray-900">Collaboration</h2>
          <p className="text-gray-600">Manage who can access and edit this app</p>
        </div>

        {/* Invite New Collaborator - Only show to owners */}
        {isOwner ? (
          <div className="bg-white shadow rounded-lg">
            <div className="px-6 py-4 border-b border-gray-200">
              <h3 className="text-lg font-medium text-gray-900 flex items-center">
                <span className="text-indigo-400 text-xl mr-2">👥</span>
                Invite Collaborator
              </h3>
              <p className="text-sm text-gray-500 mt-1">
                Invite users to collaborate on this app as editors. They'll receive an email invitation.
              </p>
            </div>
            <div className="p-6">
              <CollaborationForm onSubmit={handleInviteUser} />
            </div>
          </div>
        ) : (
          <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
            <div className="flex">
              <div className="flex-shrink-0">
                <span className="text-yellow-400 text-xl">ℹ️</span>
              </div>
              <div className="ml-3">
                <h3 className="text-sm font-medium text-yellow-800">
                  Editor Access
                </h3>
                <div className="mt-2 text-sm text-yellow-700">
                  <p>
                    You have editor access to this app. Only the app owner can invite new collaborators.
                  </p>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Current Collaborators */}
        <div className="bg-white shadow rounded-lg">
          <div className="px-6 py-4 border-b border-gray-200">
            <h3 className="text-lg font-medium text-gray-900 flex items-center">
              <span className="text-indigo-400 text-xl mr-2">🤝</span>
              Current Collaborators ({collaborators.length})
            </h3>
            <p className="text-sm text-gray-500 mt-1">
              {isOwner ? 'Manage existing collaborators and their permissions' : 'View current collaborators'}
            </p>
          </div>
          
          {collaborators.length > 0 ? (
            <div className="overflow-hidden">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      User
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Role
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Status
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Invited
                    </th>
                    {isOwner && (
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                        Actions
                      </th>
                    )}
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-200">
                  {collaborators.map((collaborator) => (
                    <tr key={collaborator.id} className="hover:bg-gray-50">
                      <td className="px-6 py-4 whitespace-nowrap">
                        <div className="flex items-center">
                          <div className="flex-shrink-0 h-8 w-8">
                            <div className="h-8 w-8 rounded-full bg-indigo-500 flex items-center justify-center">
                              <span className="text-sm font-medium text-white">
                                {collaborator.user_email.charAt(0).toUpperCase()}
                              </span>
                            </div>
                          </div>
                          <div className="ml-3">
                            <div className="text-sm font-medium text-gray-900">
                              {collaborator.user_name || collaborator.user_email}
                            </div>
                            {collaborator.user_name && (
                              <div className="text-sm text-gray-500">
                                {collaborator.user_email}
                              </div>
                            )}
                          </div>
                        </div>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <span className={`inline-flex px-2 py-1 text-xs font-semibold rounded-full ${getRoleBadge(collaborator.role)}`}>
                          {collaborator.role.charAt(0).toUpperCase() + collaborator.role.slice(1)}
                        </span>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <span className={`inline-flex px-2 py-1 text-xs font-semibold rounded-full ${getStatusBadge(collaborator.status)}`}>
                          {collaborator.status.charAt(0).toUpperCase() + collaborator.status.slice(1)}
                        </span>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                        <div>
                          {new Date(collaborator.invited_at).toLocaleDateString()}
                        </div>
                        <div className="text-xs">
                          by {collaborator.invited_by_name || 'Unknown'}
                        </div>
                      </td>
                      {isOwner && (
                        <td className="px-6 py-4 whitespace-nowrap text-sm font-medium">
                          <div className="flex space-x-2">
                            {collaborator.status === 'accepted' && collaborator.role !== 'owner' && (
                              <select
                                value={collaborator.role}
                                onChange={(e) => handleUpdateRole(collaborator.user_id, e.target.value)}
                                className="text-xs border border-gray-300 rounded px-2 py-1 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                              >
                                <option value="editor">Editor</option>
                              </select>
                            )}
                            {collaborator.role !== 'owner' && (
                              <button 
                                onClick={() => handleRemoveCollaborator(collaborator.user_id)}
                                className="text-red-600 hover:text-red-900 transition-colors"
                              >
                                Remove
                              </button>
                            )}
                          </div>
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="text-center py-8">
              <div className="text-4xl mb-4">👥</div>
              <h3 className="text-lg font-semibold text-gray-900 mb-2">No Collaborators Yet</h3>
              <p className="text-gray-600">
                {isOwner 
                  ? "This app doesn't have any collaborators. Invite users above to start sharing."
                  : "This app doesn't have any other collaborators yet."
                }
              </p>
            </div>
          )}
        </div>

        {/* Information Boxes */}
        <div className="space-y-4">
          {/* Collaboration Info */}
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
            <div className="flex">
              <div className="flex-shrink-0">
                <span className="text-blue-400 text-xl">💡</span>
              </div>
              <div className="ml-3">
                <h3 className="text-sm font-medium text-blue-800">
                  About Collaboration
                </h3>
                <div className="mt-2 text-sm text-blue-700">
                  <p>
                    Collaboration allows multiple users to work on the same app. Invited users will 
                    receive an email invitation and can access the app once they accept.
                    {!isOwner && " You can leave this collaboration anytime from the apps list."}
                  </p>
                </div>
              </div>
            </div>
          </div>

          {/* Security Notice */}
          <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
            <div className="flex">
              <div className="flex-shrink-0">
                <span className="text-yellow-400 text-xl">🔒</span>
              </div>
              <div className="ml-3">
                <h3 className="text-sm font-medium text-yellow-800">
                  Collaboration Rules
                </h3>
                <div className="mt-2 text-sm text-yellow-700">
                  <ul className="list-disc list-inside space-y-1">
                    <li>Only app owners can invite new collaborators</li>
                    <li>All new collaborators are invited as editors</li>
                    <li>Editors can modify app content but cannot manage collaborators</li>
                    <li>Owners have full control and can remove collaborators</li>
                    {!isOwner && <li>You can leave this collaboration from the main apps list</li>}
                  </ul>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </SettingsLayout>
  );
}

export default CollaborationPage; 