import { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
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
import { FormSelect } from '../../components/ui/FormField';
import ButtonApp from '../../components/ui/ButtonApp';
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
  const { t, i18n } = useTranslation('common');
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
      setError(err instanceof Error ? err.message : t('collaborationPage.errors.loadFailed'));
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
      setError(err instanceof Error ? err.message : t('collaborationPage.errors.loadFailed'));
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
        loading: t('collaborationPage.notifications.sendingInvitation'),
        success: t('collaborationPage.notifications.invitationSent', { email }),
        error: () => t('collaborationPage.errors.sendInvitationFailed'),
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
        loading: t('collaborationPage.notifications.updatingRole'),
        success: t('collaborationPage.notifications.roleUpdated'),
        error: (err) => errorMessage(err, t('collaborationPage.errors.updateRoleFailed')),
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
      title: t('collaborationPage.remove.title'),
      message: target
        ? t('collaborationPage.remove.namedMessage', { name: target.user_name || target.user_email })
        : t('collaborationPage.remove.message'),
      variant: 'danger',
      confirmLabel: t('collaborationPage.actions.remove'),
    });
    if (!ok) return;

    const result = await mutate(
      () => apiService.removeCollaborator(Number.parseInt(appId), userId),
      {
        loading: t('collaborationPage.notifications.removingCollaborator'),
        success: t('collaborationPage.notifications.collaboratorRemoved'),
        error: (err) => errorMessage(err, t('collaborationPage.errors.removeCollaboratorFailed')),
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

  const getRoleLabel = (role: string) => t(`collaborationPage.roles.${role.toLowerCase()}`, {
    defaultValue: role.charAt(0).toUpperCase() + role.slice(1),
  });

  const getStatusLabel = (status: string) => t(`collaborationPage.status.${status.toLowerCase()}`, {
    defaultValue: status.charAt(0).toUpperCase() + status.slice(1),
  });

  if (loading) {
    return (
      
        <LoadingState variant="page" message={t('collaborationPage.loading')} />
      
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
            {' '}{t('collaborationPage.invite.title')}
          </h3>
          <p className="text-sm text-fg-secondary dark:text-fg-secondary-dark mt-1">
            {t('collaborationPage.invite.description')}
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
        title={t('collaborationPage.access.title')}
        message={t('collaborationPage.access.message')}
      />
    );
  }

  return (
    
      <div className="p-6 space-y-8">
        {/* Header */}
        <Title variant="titSecundario" titulo={t('collaborationPage.title')} subtitulo={t('collaborationPage.subtitle')} />

        {!canManage && <ReadOnlyBanner userRole={userRole} minRole={AppRole.ADMINISTRATOR} />}

        {inviteCollaboratorSection}

        {/* Current Collaborators */}
        <div>
          <h3 className="font-display text-lg font-normal text-fg dark:text-fg-dark flex items-center">
            <Handshake className="w-5 h-5 text-bronze dark:text-bronze-dark mr-2" />
            {t('collaborationPage.teamMembers', { count: allMembers.length })}
          </h3>
          <p className="text-sm text-fg-secondary dark:text-fg-secondary-dark mt-1">
            {canManage ? t('collaborationPage.team.manageDescription') : t('collaborationPage.team.viewDescription')}
          </p>
          
          <Table
            className="mt-4"
            stickyEdgeColumns
            data={allMembers}
            keyExtractor={(member) => member.id.toString()}
            columns={[
              {
                header: t('collaborationPage.table.user'),
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
                            ({t('collaborationPage.you')})
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
                header: t('collaborationPage.table.role'),
                render: (member) => (
                  <div className="flex items-center gap-1">
                    
                    {member.role === 'owner' ? (
                      <Badge
                        label={t('collaborationPage.roles.owner')}
                        variant="secondary"
                        icon={<Crown className="w-3 h-3" />}
                      />
                    ) : (
                      <Badge
                        label={getRoleLabel(member.role)}
                        variant="custom"
                        className={getRoleBadge(member.role)}
                      />
                      
                    )}
                    {member.platform_role === 'viewer' && member.role !== 'viewer' && member.role !== 'owner' && (
                      <span className="relative group inline-flex items-center">
                        <AlertTriangle className="w-3.5 h-3.5 text-bronze dark:text-bronze-dark cursor-help flex-shrink-0" />
                        <span className="pointer-events-none absolute left-full ml-2 top-1/2 -translate-y-1/2 hidden group-hover:block w-56 rounded-lg bg-bronze-bg border border-bronze-border dark:bg-bronze-bg-dark dark:border-bronze-border-dark px-3 py-2.5 text-xs shadow-md z-50">
                          <span className="block font-semibold text-bronze-strong dark:text-bronze-strong-dark mb-1">{t('collaborationPage.platformViewer.title')}</span>
                          <span className="text-bronze dark:text-bronze-dark leading-relaxed whitespace-normal">{t('collaborationPage.platformViewer.description')}</span>
                        </span>
                      </span>
                    )}
                  </div>
                )
              },
              {
                header: t('collaborationPage.table.status'),
                render: (member) => (
                  member.role === 'owner' ? (
                    <StatusBadge status="active" customLabel={t('collaborationPage.status.active')} />
                  ) : (
                    <StatusBadge
                      status={getStatusType(member.status)}
                      customLabel={getStatusLabel(member.status)}
                    />
                  )
                )
              },
              {
                header: t('collaborationPage.table.since'),
                render: (member) => (
                  member.role === 'owner' ? (
                    <div className="text-xs text-fg-secondary dark:text-fg-secondary-dark">
                      {t('collaborationPage.appCreator')}
                    </div>
                  ) : (
                    <div className="text-xs text-fg-secondary dark:text-fg-secondary-dark">
                      {new Date(member.invited_at).toLocaleDateString(i18n.resolvedLanguage)}<br />
                      {t('collaborationPage.invitedBy', { name: member.invited_by_name || t('collaborationPage.unknown') })}
                    </div>
                  )
                ),
                className: 'px-6 py-4 whitespace-nowrap text-sm text-gray-500'
              },
              ...(canManage ? [{
                header: t('collaborationPage.table.actions'),
                sticky: 'right' as const,
                render: (member: Collaborator) => (
                  member.role === 'owner' ? (
                    <span className="text-gray-400">-</span>
                  ) : (
                    <div className="flex space-x-2">
                      {member.status === 'accepted' && member.role !== 'owner' && (
                        <FormSelect
                          label={t('collaborationPage.table.role')}
                          labelClassName="sr-only"
                          id={`collaborator-role-${member.user_id}`}
                          value={member.role}
                          onChange={(e) => void handleUpdateRole(member.user_id, e.target.value)}
                          disabled={member.platform_role === 'viewer'}
                          title={member.platform_role === 'viewer' ? t('collaborationPage.platformViewer.cannotPromote') : undefined}
                          className="min-w-32"
                          options={[
                            ...(member.platform_role !== 'viewer'
                              ? [
                                  { value: 'editor', label: t('collaborationPage.roles.editor') },
                                  { value: 'administrator', label: t('collaborationPage.roles.administrator') },
                                ]
                              : []),
                            { value: 'viewer', label: t('collaborationPage.roles.viewer') },
                          ]}
                        />
                      )}
                      {member.role !== 'owner' && (
                        <ButtonApp
                          label={t('collaborationPage.actions.remove')}
                          onClick={() => void handleRemoveCollaborator(member.user_id)}
                          variant="dangerSolid"
                          size="small"
                        />
                      )}
                    </div>
                  )
                ),
                className: 'px-6 py-4 whitespace-nowrap text-sm font-medium'
              }] : [])
            ]}
            rowClassName={(member) => member.role === 'owner' ? "bg-surface-tint dark:bg-surface-tint-dark" : ""}
            emptyIcon={<Users className="w-10 h-10 text-gray-300" />}
            emptyMessage={t('collaborationPage.empty.title')}
            emptySubMessage={canManage 
              ? t('collaborationPage.empty.manageMessage')
              : t('collaborationPage.empty.viewMessage')}
            loading={loading}
          />
        </div>

        {/* Information Boxes */}
        <div className="space-y-4">
          {/* Collaboration Info */}
          <Alert
            type="info"
            title={t('collaborationPage.about.title')}
            message={(
              <>
                {t('collaborationPage.about.description')}
                {!isOwner && <> {t('collaborationPage.about.leaveNotice')}</>}
              </>
            )}
          />

          {/* Security Notice */}
          <Alert
            type="warning"
            title={t('collaborationPage.rules.title')}
            message={(
              <ul className="list-disc list-inside space-y-1">
                <li>{t('collaborationPage.rules.ownerInvites')}</li>
                <li>{t('collaborationPage.rules.invitedRoles')}</li>
                <li>{t('collaborationPage.rules.administratorPermissions')}</li>
                <li>{t('collaborationPage.rules.editorPermissions')}</li>
                <li>{t('collaborationPage.rules.ownerPermissions')}</li>
                {!isOwner && <li>{t('collaborationPage.rules.leave')}</li>}
              </ul>
            )}
          />
        </div>
      </div>
    
  );
}

export default CollaborationPage;