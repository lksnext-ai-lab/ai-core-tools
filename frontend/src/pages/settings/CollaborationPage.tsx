import { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { Users, Handshake, Crown, AlertTriangle } from 'lucide-react';
import CollaborationForm from '../../components/forms/CollaborationForm';
import { apiService } from '../../services/api';
import { useUser } from '../../contexts/UserContext';
import { useSettingsCache } from '../../contexts/SettingsCacheContext';
import { useAppRole } from '../../hooks/useAppRole';
import { AppRole } from '../../types/roles';
import ReadOnlyBanner from '../../components/ui/ReadOnlyBanner';
import Alert from '../../components/ui/Alert';
import Table from '../../components/ui/Table';
import { Badge, StatusBadge, type StatusType } from '../../components/ui/Badge';
import { useConfirm } from '../../contexts/ConfirmContext';
import { useApiMutation } from '../../hooks/useApiMutation';
import { errorMessage } from '../../constants/messages';
import { LoadingState } from '../../components/ui/LoadingState';
import { Title } from '../../components/ui/Title';
import { CardApp } from '../..';

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
  platform_role?: string;
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
  const confirm = useConfirm();
  const mutate = useApiMutation();

  const [collaborators, setCollaborators] = useState<Collaborator[]>([]);
  const [allMembers, setAllMembers] = useState<Collaborator[]>([]); // Owner + Collaborators
  const [appOwner, setAppOwner] = useState<AppOwner | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  const { hasMinRole, userRole } = useAppRole(appId);
  const canManage = hasMinRole(AppRole.ADMINISTRATOR);
  const isOwner = userRole === AppRole.OWNER;

  // Load collaborators and app info from cache or API
  useEffect(() => {
    const loadData = async () => {
      await loadCollaborators(); // This will also load owner info
    };
    void loadData();
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
      const appData = await apiService.getApp(Number.parseInt(appId));
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
      const response = await apiService.getCollaborators(Number.parseInt(appId));
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
      const response = await apiService.getCollaborators(Number.parseInt(appId));
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

  async function handleInviteUser(email: string, role: string) {
    if (!appId) return;

    const result = await mutate(
      () => apiService.inviteCollaborator(Number.parseInt(appId), email, role),
      {
        loading: 'Sending invitation…',
        success: `Invitation sent to ${email}`,
        error: (err) => errorMessage(err, 'Failed to send invitation'),
      },
    );
    if (result === undefined) return;

    settingsCache.invalidateCollaborators(appId);
    try {
      await forceReloadCollaborators();
    } catch (err) {
      console.error('Refetch after invite failed:', err);
    }
  }

  async function handleUpdateRole(userId: number, newRole: string) {
    if (!appId) return;

    const result = await mutate(
      () => apiService.updateCollaboratorRole(Number.parseInt(appId), userId, newRole),
      {
        loading: 'Updating role…',
        success: 'Role updated',
        error: (err) => errorMessage(err, 'Failed to update role'),
      },
    );
    if (result === undefined) return;

    settingsCache.invalidateCollaborators(appId);
    try {
      await forceReloadCollaborators();
    } catch (err) {
      console.error('Refetch after role update failed:', err);
    }
  }

  async function handleRemoveCollaborator(userId: number) {
    if (!appId) return;

    const target = collaborators.find((c) => c.user_id === userId);
    const ok = await confirm({
      title: 'Remove collaborator?',
      message: target
        ? `Remove ${target.user_name || target.user_email} from this app? They will lose access immediately.`
        : 'Remove this collaborator? They will lose access to this app.',
      variant: 'danger',
      confirmLabel: 'Remove',
    });
    if (!ok) return;

    const result = await mutate(
      () => apiService.removeCollaborator(Number.parseInt(appId), userId),
      {
        loading: 'Removing collaborator…',
        success: 'Collaborator removed',
        error: (err) => errorMessage(err, 'Failed to remove collaborator'),
      },
    );
    if (result === undefined) return;

    const newCollaborators = collaborators.filter((c) => c.user_id !== userId);
    setCollaborators(newCollaborators);
    settingsCache.setCollaborators(appId, newCollaborators);
  }

  const getStatusType = (status: string): StatusType => {
    switch (status.toLowerCase()) {
      case 'accepted':
        return 'active';
      case 'pending':
        return 'pending';
      case 'declined':
        return 'error';
      default:
        return 'inactive';
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
      case 'viewer':
        return 'bg-yellow-100 text-yellow-800';
      default:
        return 'bg-gray-100 text-gray-800';
    }
  };

  if (loading) {
    return (
      
        <LoadingState variant="page" message="Loading collaboration settings..." />
      
    );
  }

  if (error) {
    return (
      <div className="p-6">
        <Alert type="error" message={error} onDismiss={() => loadCollaborators()} />
      </div>
    );
  }

  // Invite New Collaborator - Only show to admins/owners
  let inviteCollaboratorSection;
  if (canManage) {
    inviteCollaboratorSection = (
      <CardApp className="px-6 py-4">
        <h3 className="font-display text-lg font-normal text-fg dark:text-fg-dark flex items-center">
            <Users className="w-5 h-5 text-bronze dark:text-bronze-dark mr-2" />
            {' '}Invite Collaborator
          </h3>
          <p className="text-sm text-fg-secondary dark:text-fg-secondary-dark mt-1">
            Invite users to collaborate on this app. They'll receive an email invitation.
          </p>
      
        <div className="py-6">
          <CollaborationForm onSubmit={handleInviteUser} />
        </div>
      </CardApp>
    );
  } else {
    inviteCollaboratorSection = (
      <Alert
        type="warning"
        title="Collaborator Access"
        message="You have collaborator access to this app. Only administrators can invite new collaborators."
      />
    );
  }

  return (
    
      <div className="p-6 space-y-8">
        {/* Header */}
        <Title variant='titSecundario' titulo='Collaboration' subtitulo='Manage team access and permissions for this app'/>

        {!canManage && <ReadOnlyBanner userRole={userRole} minRole={AppRole.ADMINISTRATOR} />}

        {inviteCollaboratorSection}

        {/* Current Collaborators */}
        <div>
          <h3 className="font-display text-lg font-normal text-fg dark:text-fg-dark flex items-center">
            <Handshake className="w-5 h-5 text-bronze dark:text-bronze-dark mr-2" />
            Team Members ({allMembers.length})
          </h3>
          <p className="text-sm text-fg-secondary dark:text-fg-secondary-dark mt-1">
            {canManage ? 'Manage existing collaborators and their permissions' : 'View team members and their roles'}
          </p>
          
          <Table
            className="mt-4"
            data={allMembers}
            keyExtractor={(member) => member.id.toString()}
            columns={[
              {
                header: 'User',
                render: (member) => (
                  <div className="flex items-center">
                    <div className="flex-shrink-0 h-8 w-8">
                      <div className={`h-8 w-8 rounded-full bg-ink-on-dark dark:bg-ink-on flex items-center justify-center`}>
                        <span className="text-sm font-medium text-ink-on dark:text-ink-on-dark">
                          {member.user_email.charAt(0).toUpperCase()}
                        </span>
                      </div>
                    </div>
                    <div className="ml-3">
                      <div className="text-sm font-medium text-fg dark:text-fg-dark flex items-center">
                        {member.user_name || member.user_email}
                        {user?.user_id === member.user_id && (
                          <span className="ml-2 text-xs font-semibold text-fg dark:text-fg-dark">
                            (You)
                          </span>
                        )}
                      </div>
                      {member.user_name && (
                        <div className="text-sm text-fg-secondary dark:text-fg-secondary-dark">
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
                  <div className="flex items-center gap-1">
                    {member.role === 'owner' ? (
                      <Badge
                        label="Owner"
                        variant="secondary"
                        icon={<Crown className="w-3 h-3" />}
                      />
                    ) : (
                      <Badge
                        label={member.role.charAt(0).toUpperCase() + member.role.slice(1)}
                        variant="custom"
                        className={getRoleBadge(member.role)}
                      />
                    )}
                    {member.platform_role === 'viewer' && member.role !== 'viewer' && member.role !== 'owner' && (
                      <span className="relative group inline-flex items-center">
                        <AlertTriangle className="w-3.5 h-3.5 text-amber-500 cursor-help flex-shrink-0" />
                        <span className="pointer-events-none absolute left-full ml-2 top-1/2 -translate-y-1/2 hidden group-hover:block w-56 rounded-lg bg-yellow-50 border border-yellow-200 px-3 py-2.5 text-xs shadow-md z-50">
                          <span className="block font-semibold text-amber-700 mb-1">Platform viewer</span>
                          <span className="block text-gray-600 leading-relaxed whitespace-normal">This user can only see agents published in the marketplace. They cannot edit app content.</span>
                        </span>
                      </span>
                    )}
                  </div>
                )
              },
              {
                header: 'Status',
                render: (member) => (
                  member.role === 'owner' ? (
                    <StatusBadge status="active" customLabel="Active" />
                  ) : (
                    <StatusBadge
                      status={getStatusType(member.status)}
                      customLabel={member.status.charAt(0).toUpperCase() + member.status.slice(1)}
                    />
                  )
                )
              },
              {
                header: 'Since',
                render: (member) => (
                  member.role === 'owner' ? (
                    <div className="text-xs text-fg-secondary dark:text-fg-secondary-dark">
                      App creator
                    </div>
                  ) : (
                    <>
                      <div className="text-xs text-fg-secondary dark:text-fg-secondary-dark">
                        {new Date(member.invited_at).toLocaleDateString()}<br />
                        by {member.invited_by_name || 'Unknown'}
                      </div>
                    </>
                  )
                ),
                className: 'px-6 py-4 whitespace-nowrap text-sm text-gray-500'
              },
              ...(canManage ? [{
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
                          disabled={member.platform_role === 'viewer'}
                          title={member.platform_role === 'viewer' ? 'Viewer platform role — cannot be promoted' : undefined}
                          className="text-xs border border-gray-300 rounded px-2 py-1 focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:bg-gray-50 disabled:text-gray-400 disabled:cursor-not-allowed"
                        >
                          {member.platform_role !== 'viewer' && <option value="editor">Editor</option>}
                          {member.platform_role !== 'viewer' && <option value="administrator">Administrator</option>}
                          <option value="viewer">Viewer</option>
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
            rowClassName={(member) => member.role === 'owner' ? "bg-surface-tint dark:bg-surface-tint-dark" : ""}
            emptyIcon={<Users className="w-10 h-10 text-gray-300" />}
            emptyMessage="No Collaborators Yet"
            emptySubMessage={canManage 
              ? "This app doesn't have any collaborators. Invite users above to start sharing."
              : "This app doesn't have any other collaborators yet."}
            loading={loading}
          />
        </div>

        {/* Information Boxes */}
        <div className="space-y-4">
          {/* Collaboration Info */}
          <Alert
            type="info"
            title="About Collaboration"
            message={(
              <>
                Collaboration allows multiple users to work on the same app. Invited users will
                receive an email invitation and can access the app once they accept.
                {!isOwner && " You can leave this collaboration anytime from the apps list."}
              </>
            )}
          />

          {/* Security Notice */}
          <Alert
            type="warning"
            title="Collaboration Rules"
            message={(
              <ul className="list-disc list-inside space-y-1">
                <li>Only app owners can invite new collaborators</li>
                <li>Collaborators can be invited as editors or administrators</li>
                <li>Administrators have the same permissions as owners except managing collaborators</li>
                <li>Editors can modify app content but cannot manage collaborators or settings</li>
                <li>Owners have full control and can manage all collaborators</li>
                {!isOwner && <li>You can leave this collaboration from the main apps list</li>}
              </ul>
            )}
          />
        </div>
      </div>
    
  );
}

export default CollaborationPage;