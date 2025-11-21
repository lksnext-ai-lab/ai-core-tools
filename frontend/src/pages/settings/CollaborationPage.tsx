import { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import CollaborationForm from '../../components/forms/CollaborationForm';
import { apiService } from '../../services/api';
import { useUser } from '../../contexts/UserContext';
import { useSettingsCache } from '../../contexts/SettingsCacheContext';
import Alert from '../../components/ui/Alert';
import Table from '../../components/ui/Table';

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

interface AppOwner {
  id: number;
  email: string;
  name?: string;
}

function CollaborationPage() {
  const { appId } = useParams();
  const { user } = useUser();
  const settingsCache = useSettingsCache();

  const [collaborators, setCollaborators] = useState<Collaborator[]>([]);
  const [allMembers, setAllMembers] = useState<Collaborator[]>([]); // Owner + Collaborators
  const [appOwner, setAppOwner] = useState<AppOwner | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [currentUserRole, setCurrentUserRole] = useState<string | null>(null);

  // Load collaborators and app info from cache or API
  useEffect(() => {
    const loadData = async () => {
      await loadCollaborators(); // This will also load owner info
    };
    loadData();
    checkUserRole();
  }, [appId]);

  // Combine owner and collaborators whenever they change
  useEffect(() => {
    const members: Collaborator[] = [];
    
    // Add owner as first member if exists
    if (appOwner?.email) { // Only add if we have email (complete data)
      members.push({
        id: -1, // Special ID for owner
        user_id: appOwner.id,
        user_email: appOwner.email,
        user_name: appOwner.name,
        role: 'owner',
        status: 'accepted',
        invited_at: '', // Owner doesn't have invited_at
        invited_by_name: undefined
      });
    }
    
    // Add all collaborators
    members.push(...collaborators);
    
    setAllMembers(members);
  }, [appOwner, collaborators]);

  async function loadOwnerInfo(collaboratorsList: Collaborator[]) {
    if (!appId) return;
    
    try {
      // Get app data to find owner info
      const appData = await apiService.getApp(parseInt(appId));
      const ownerId = appData.owner_id;
      const ownerEmail = appData.owner_email;
      const ownerName = appData.owner_name;
      
      // Use the owner info from app data
      if (ownerId && ownerEmail) {
        setAppOwner({
          id: ownerId,
          email: ownerEmail,
          name: ownerName
        });
        return;
      }
      
      // Fallback: Check if owner is current user
      if (user?.user_id === ownerId && user) {
        setAppOwner({
          id: ownerId,
          email: user.email,
          name: user.name
        });
        return;
      }
      
      // Fallback: Try to find owner in collaborators list
      const ownerInCollabs = collaboratorsList.find(c => c.user_id === ownerId);
      if (ownerInCollabs) {
        setAppOwner({
          id: ownerId,
          email: ownerInCollabs.user_email,
          name: ownerInCollabs.user_name
        });
        return;
      }
    } catch (err) {
      console.error('Error loading owner info:', err);
    }
  }

  async function loadCollaborators() {
    if (!appId) return;
    
    // Check if we have cached data first
    const cachedData = settingsCache.getCollaborators(appId);
    if (cachedData) {
      setCollaborators(cachedData);
      
      // Also try to extract owner info from collaborators
      await loadOwnerInfo(cachedData);
      
      setLoading(false);
      return;
    }
    
    // If no cache, load from API
    try {
      setLoading(true);
      setError(null);
      const response = await apiService.getCollaborators(parseInt(appId));
      setCollaborators(response);
      
      // Also enrich owner info
      await loadOwnerInfo(response);
      
      // Cache the response
      settingsCache.setCollaborators(appId, response);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load collaborators');
      console.error('Error loading collaborators:', err);
    } finally {
      setLoading(false);
    }
  }

  async function forceReloadCollaborators() {
    if (!appId) return;
    
    try {
      setLoading(true);
      setError(null);
      const response = await apiService.getCollaborators(parseInt(appId));
      setCollaborators(response);
      
      // Also enrich owner info
      await loadOwnerInfo(response);
      
      // Cache the response
      settingsCache.setCollaborators(appId, response);
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
        // Check if user is administrator by getting collaborators
        const response = await apiService.getCollaborators(parseInt(appId));
        const myCollaboration = response.find((c: Collaborator) => c.user_id === user?.user_id);
        if (myCollaboration?.role === 'administrator') {
          setCurrentUserRole('administrator');
        } else {
          setCurrentUserRole('editor');
        }
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
      // Invalidate cache and force reload collaborators list
      settingsCache.invalidateCollaborators(appId);
      await forceReloadCollaborators();
    } catch (err) {
      throw new Error(err instanceof Error ? err.message : 'Failed to send invitation');
    }
  }

  async function handleUpdateRole(userId: number, newRole: string) {
    if (!appId) return;

    try {
      await apiService.updateCollaboratorRole(parseInt(appId), userId, newRole);
      // Invalidate cache and force reload collaborators list
      settingsCache.invalidateCollaborators(appId);
      await forceReloadCollaborators();
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
      const newCollaborators = collaborators.filter(c => c.user_id !== userId);
      setCollaborators(newCollaborators);
      // Update cache
      settingsCache.setCollaborators(appId, newCollaborators);
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
      case 'administrator':
        return 'bg-indigo-100 text-indigo-800';
      case 'editor':
        return 'bg-blue-100 text-blue-800';
      default:
        return 'bg-gray-100 text-gray-800';
    }
  };

  const isOwner = currentUserRole === 'owner';
  const isAdmin = currentUserRole === 'administrator';

  if (loading) {
    return (
      
        <div className="p-6 text-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600 mx-auto"></div>
          <p className="mt-2 text-gray-600">Loading collaboration settings...</p>
        </div>
      
    );
  }

  if (error) {
    return (
      <div className="p-6">
        <Alert type="error" message={error} onDismiss={() => loadCollaborators()} />
      </div>
    );
  }

  // Invite New Collaborator - Only show to owners
  let inviteCollaboratorSection;
  if (isOwner) {
    inviteCollaboratorSection = (
      <div className="bg-white shadow rounded-lg">
        <div className="px-6 py-4 border-b border-gray-200">
          <h3 className="text-lg font-medium text-gray-900 flex items-center">
            <span className="text-indigo-400 text-xl mr-2">👥</span>
            {' '}Invite Collaborator
          </h3>
          <p className="text-sm text-gray-500 mt-1">
            Invite users to collaborate on this app as editors. They'll receive an email invitation.
          </p>
        </div>
        <div className="p-6">
          <CollaborationForm onSubmit={handleInviteUser} />
        </div>
      </div>
    );
  } else if (isAdmin) {
    inviteCollaboratorSection = (
      <div className="bg-purple-50 border border-purple-200 rounded-lg p-4">
        <div className="flex">
          <div className="flex-shrink-0">
            <span className="text-purple-400 text-xl">ℹ️</span>
          </div>
          <div className="ml-3">
            <h3 className="text-sm font-medium text-purple-800">
              Administrator Access
            </h3>
            <div className="mt-2 text-sm text-purple-700">
              <p>
                You have administrator access to this app. Only the app owner can manage collaborators.
              </p>
            </div>
          </div>
        </div>
      </div>
    );
  } else {
    inviteCollaboratorSection = (
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
    );
  }

  return (
    
      <div className="p-6 space-y-8">
        {/* Header */}
        <div>
          <h2 className="text-xl font-semibold text-gray-900">Collaboration</h2>
          <p className="text-gray-600">Manage who can access and edit this app</p>
        </div>

        {inviteCollaboratorSection}

        {/* Current Collaborators */}
        <div className="bg-white shadow rounded-lg">
          <div className="px-6 py-4 border-b border-gray-200">
            <h3 className="text-lg font-medium text-gray-900 flex items-center">
              <span className="text-indigo-400 text-xl mr-2">🤝</span>
              Team Members ({allMembers.length})
            </h3>
            <p className="text-sm text-gray-500 mt-1">
              {isOwner ? 'Manage existing collaborators and their permissions' : 'View team members and their roles'}
            </p>
          </div>
          
          <Table
            data={allMembers}
            keyExtractor={(member) => member.id.toString()}
            columns={[
              {
                header: 'User',
                render: (member) => (
                  <div className="flex items-center">
                    <div className="flex-shrink-0 h-8 w-8">
                      <div className={`h-8 w-8 rounded-full ${member.role === 'owner' ? 'bg-blue-600' : 'bg-indigo-500'} flex items-center justify-center`}>
                        <span className="text-sm font-medium text-white">
                          {member.user_email.charAt(0).toUpperCase()}
                        </span>
                      </div>
                    </div>
                    <div className="ml-3">
                      <div className="text-sm font-medium text-gray-900 flex items-center">
                        {member.user_name || member.user_email}
                        {user?.user_id === member.user_id && (
                          <span className={`ml-2 text-xs font-semibold ${member.role === 'owner' ? 'text-blue-600' : 'text-indigo-600'}`}>
                            (You)
                          </span>
                        )}
                      </div>
                      {member.user_name && (
                        <div className="text-sm text-gray-500">
                          {member.user_email}
                        </div>
                      )}
                    </div>
                  </div>
                )
              },
              {
                header: 'Role',
                render: (member) => (
                  member.role === 'owner' ? (
                    <span className="inline-flex items-center px-2 py-1 text-xs font-semibold rounded-full bg-purple-100 text-purple-800">
                      <span className="mr-1">👑</span>
                      {' '}Owner
                    </span>
                  ) : (
                    <span className={`inline-flex px-2 py-1 text-xs font-semibold rounded-full ${getRoleBadge(member.role)}`}>
                      {member.role.charAt(0).toUpperCase() + member.role.slice(1)}
                    </span>
                  )
                )
              },
              {
                header: 'Status',
                render: (member) => (
                  member.role === 'owner' ? (
                    <span className="inline-flex px-2 py-1 text-xs font-semibold rounded-full bg-green-100 text-green-800">
                      Active
                    </span>
                  ) : (
                    <span className={`inline-flex px-2 py-1 text-xs font-semibold rounded-full ${getStatusBadge(member.status)}`}>
                      {member.status.charAt(0).toUpperCase() + member.status.slice(1)}
                    </span>
                  )
                )
              },
              {
                header: 'Since',
                render: (member) => (
                  member.role === 'owner' ? (
                    <div className="text-xs text-gray-400">
                      App creator
                    </div>
                  ) : (
                    <>
                      <div>
                        {new Date(member.invited_at).toLocaleDateString()}
                      </div>
                      <div className="text-xs">
                        by {member.invited_by_name || 'Unknown'}
                      </div>
                    </>
                  )
                ),
                className: 'px-6 py-4 whitespace-nowrap text-sm text-gray-500'
              },
              ...(isOwner ? [{
                header: 'Actions',
                render: (member: Collaborator) => (
                  member.role === 'owner' ? (
                    <span className="text-gray-400">-</span>
                  ) : (
                    <div className="flex space-x-2">
                      {member.status === 'accepted' && member.role !== 'owner' && (
                        <select
                          value={member.role}
                          onChange={(e) => void handleUpdateRole(member.user_id, e.target.value)}
                          className="text-xs border border-gray-300 rounded px-2 py-1 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                        >
                          <option value="editor">Editor</option>
                          <option value="administrator">Administrator</option>
                        </select>
                      )}
                      {member.role !== 'owner' && (
                        <button 
                          onClick={() => void handleRemoveCollaborator(member.user_id)}
                          className="text-red-600 hover:text-red-900 transition-colors"
                        >
                          Remove
                        </button>
                      )}
                    </div>
                  )
                ),
                className: 'px-6 py-4 whitespace-nowrap text-sm font-medium'
              }] : [])
            ]}
            rowClassName={(member) => member.role === 'owner' ? "bg-blue-50" : "hover:bg-gray-50"}
            emptyIcon="👥"
            emptyMessage="No Collaborators Yet"
            emptySubMessage={isOwner 
              ? "This app doesn't have any collaborators. Invite users above to start sharing."
              : "This app doesn't have any other collaborators yet."}
            loading={loading}
          />
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
                    <li>Collaborators can be invited as editors or administrators</li>
                    <li>Administrators have the same permissions as owners except managing collaborators</li>
                    <li>Editors can modify app content but cannot manage collaborators or settings</li>
                    <li>Owners have full control and can manage all collaborators</li>
                    {!isOwner && <li>You can leave this collaboration from the main apps list</li>}
                  </ul>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    
  );
}

export default CollaborationPage;