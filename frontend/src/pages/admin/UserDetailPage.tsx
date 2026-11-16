import { useCallback, useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import {
  ArrowLeft,
  Ban,
  Link2,
  RefreshCcw,
  Shield,
  Trash2,
  UserCheck,
} from 'lucide-react';
import Alert from '../../components/ui/Alert';
import DeleteUserDialog from '../../components/admin/DeleteUserDialog';
import OneTimeLinkModal from '../../components/ui/OneTimeLinkModal';
import { useConfirm } from '../../contexts/ConfirmContext';
import { useDeploymentMode } from '../../contexts/DeploymentModeContext';
import { useUser } from '../../contexts/UserContext';
import { errorMessage } from '../../constants/messages';
import { useApiMutation } from '../../hooks/useApiMutation';
import { ApiError } from '../../services/api';
import { adminService, OwnedAppsError } from '../../services/admin';
import type { User, UserDetail } from '../../services/admin';

type DetailState =
  | { readonly userId: number | null; readonly status: 'loading' }
  | { readonly userId: number | null; readonly status: 'not-found' }
  | { readonly userId: number | null; readonly status: 'error'; readonly message: string }
  | { readonly userId: number; readonly status: 'success'; readonly detail: UserDetail };

interface ResetLinkState {
  readonly token: string;
  readonly expiresAt: string;
}

export interface SectionCardProps {
  readonly title: string;
  readonly description?: string;
  readonly children: ReactNode;
}

function formatDate(value: string | null | undefined): string {
  if (!value) return 'Unavailable';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? 'Unavailable' : date.toLocaleString();
}

function unavailable(value: string | null | undefined): string {
  return value ?? 'Unavailable';
}

function SectionCard({ title, description, children }: SectionCardProps) {
  return (
    <section className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm dark:border-slate-700 dark:bg-slate-800">
      <h2 className="mb-4 text-lg font-semibold text-gray-900 dark:text-slate-100">{title}</h2>
      {description && <p className="-mt-2 mb-4 text-sm leading-6 text-gray-600 dark:text-slate-400">{description}</p>}
      {children}
    </section>
  );
}

function UserDetailPage() {
  const { userId: routeUserId } = useParams<{ userId: string }>();
  const parsedUserId = Number(routeUserId);
  const userId = Number.isSafeInteger(parsedUserId) && parsedUserId > 0 ? parsedUserId : null;
  const confirm = useConfirm();
  const mutate = useApiMutation();
  const navigate = useNavigate();
  const { user: currentUser } = useUser();
  const { authMode, isLoading: modeLoading } = useDeploymentMode();
  const isLocalMode = !modeLoading && authMode === 'local';

  const [detailState, setDetailState] = useState<DetailState | null>(null);
  const [pendingAction, setPendingAction] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);
  const [resetLinkState, setResetLinkState] = useState<ResetLinkState | null>(null);
  const [deleteDialogUser, setDeleteDialogUser] = useState<User | null>(null);
  const requestIdRef = useRef(0);
  const actionLockRef = useRef(false);
  const routeUserIdRef = useRef(userId);
  routeUserIdRef.current = userId;

  const loadDetail = useCallback(async (requestedUserId = userId): Promise<boolean> => {
    if (requestedUserId === null) {
      setDetailState({ userId: null, status: 'not-found' });
      return false;
    }
    if (routeUserIdRef.current !== requestedUserId) return false;

    const requestId = ++requestIdRef.current;
    setDetailState({ userId: requestedUserId, status: 'loading' });
    try {
      const detail = await adminService.getUser(requestedUserId);
      if (requestId !== requestIdRef.current || routeUserIdRef.current !== requestedUserId) return false;
      setDetailState({ userId: requestedUserId, status: 'success', detail });
      return true;
    } catch (error: unknown) {
      if (requestId !== requestIdRef.current || routeUserIdRef.current !== requestedUserId) return false;
      if (error instanceof ApiError && error.status === 404) {
        setDetailState({ userId: requestedUserId, status: 'not-found' });
      } else {
        setDetailState({
          userId: requestedUserId,
          status: 'error',
          message: errorMessage(error, 'Unable to load this user.'),
        });
      }
      return false;
    }
  }, [userId]);

  const refreshDetail = useCallback(async (targetUserId: number): Promise<UserDetail | null> => {
    if (routeUserIdRef.current !== targetUserId) return null;
    try {
      const latestDetail = await adminService.getUser(targetUserId);
      if (routeUserIdRef.current !== targetUserId) return null;
      setDetailState({ userId: targetUserId, status: 'success', detail: latestDetail });
      return latestDetail;
    } catch (error: unknown) {
      if (routeUserIdRef.current === targetUserId) {
        setActionError(`The action completed, but the latest user details could not be loaded: ${errorMessage(error, 'Unknown error')}`);
      }
      return null;
    }
  }, []);

  useEffect(() => {
    setResetLinkState(null);
    setDeleteDialogUser(null);
    setActionError(null);
    setActionSuccess(null);
    if (userId === null) {
      setDetailState({ userId: null, status: 'not-found' });
      return;
    }
    void loadDetail();
    return () => {
      requestIdRef.current += 1;
    };
  }, [loadDetail, userId]);

  const visibleState: DetailState =
    detailState?.userId === userId ? detailState : { userId, status: userId === null ? 'not-found' : 'loading' };
  const detail = visibleState.status === 'success' ? visibleState.detail : null;
  const identity = detail?.identity;
  const isSelf = identity !== undefined && currentUser?.user_id === identity.user_id;
  const isProtectedTarget = identity?.is_omniadmin === true;
  const actionsRestricted = isSelf || isProtectedTarget;
  const displayName = identity?.name || identity?.email || 'User';
  const ownedAppCount = detail?.owned_apps.length ?? 0;

  async function runMutation(
    targetUserId: number,
    action: string,
    operation: () => Promise<{ message: string }>,
    successFallback: string,
    confirmOptions?: Parameters<typeof confirm>[0],
  ): Promise<void> {
    if (actionLockRef.current) return;
    actionLockRef.current = true;
    setPendingAction(action);
    setActionError(null);
    setActionSuccess(null);

    try {
      if (confirmOptions && !(await confirm(confirmOptions))) return;
      if (routeUserIdRef.current !== targetUserId) return;
      const result = await mutate(operation, {
        loading: `${action}…`,
        success: (data) => data.message || successFallback,
        error: (error) => {
          const message = errorMessage(error, `${action} failed.`);
          if (routeUserIdRef.current === targetUserId) setActionError(message);
          return message;
        },
      });
      if (!result) return;

      if (routeUserIdRef.current !== targetUserId) return;
      const refreshed = await refreshDetail(targetUserId);
      if (refreshed && routeUserIdRef.current === targetUserId) setActionSuccess(result.message || successFallback);
    } finally {
      actionLockRef.current = false;
      setPendingAction(null);
    }
  }

  async function handleSetPlatformRole(role: 'viewer' | 'editor' | 'admin'): Promise<void> {
    if (!identity) return;
    const roleLabels: Record<typeof role, string> = {
      viewer: 'Viewer',
      editor: 'Editor',
      admin: 'Admin',
    };
    const downgradeWarning = role === 'viewer' && ownedAppCount > 0;
    await runMutation(
      identity.user_id,
      'Updating role',
      () => adminService.setPlatformRole(identity.user_id, role),
      'Platform role updated.',
      {
        title: `Set role to ${roleLabels[role]}?`,
        message: downgradeWarning
          ? `${displayName} owns ${ownedAppCount} app${ownedAppCount === 1 ? '' : 's'}. As a viewer, they will no longer be able to modify them but will retain ownership. Continue?`
          : `Change ${displayName}'s platform role to ${roleLabels[role]}?`,
        variant: downgradeWarning ? 'warning' : undefined,
        confirmLabel: 'Confirm',
      },
    );
  }

  async function handleDeactivate(): Promise<void> {
    if (!identity) return;
    await runMutation(
      identity.user_id,
      'Deactivating user',
      () => adminService.deactivateUser(identity.user_id),
      'User deactivated.',
      {
        title: 'Deactivate user?',
        message: `Deactivate ${displayName}? They will not be able to access the system until reactivated.`,
        variant: 'warning',
        confirmLabel: 'Deactivate',
      },
    );
  }

  async function handleActivate(): Promise<void> {
    if (!identity) return;
    await runMutation(
      identity.user_id,
      'Activating user',
      () => adminService.activateUser(identity.user_id),
      'User activated.',
    );
  }

  async function handleResetQuota(): Promise<void> {
    if (!identity) return;
    await runMutation(
      identity.user_id,
      'Resetting marketplace quota',
      () => adminService.resetUserMarketplaceQuota(identity.user_id),
      'Marketplace quota reset.',
      {
        title: 'Reset marketplace quota?',
        message: `Reset the marketplace call quota for ${displayName}? Their current-month counter will be set to 0, allowing them to make up to the full quota again.`,
        variant: 'warning',
        confirmLabel: 'Reset quota',
      },
    );
  }

  async function handleResetLink(): Promise<void> {
    if (!identity || actionLockRef.current) return;
    const targetUserId = identity.user_id;
    actionLockRef.current = true;
    setPendingAction('reset-link');
    setActionError(null);
    setActionSuccess(null);
    try {
      const result = await adminService.issueResetLink(targetUserId);
      if (routeUserIdRef.current !== targetUserId) return;
      setResetLinkState({ token: result.set_password_token, expiresAt: result.expires_at });
      setActionSuccess('Password reset link generated.');
      await refreshDetail(targetUserId);
    } catch (error: unknown) {
      if (routeUserIdRef.current === targetUserId) {
        setActionError(`Failed to issue reset link: ${errorMessage(error, 'Unknown error')}`);
      }
    } finally {
      actionLockRef.current = false;
      setPendingAction(null);
    }
  }

  function toDeleteDialogUser(source: UserDetail): User {
    if (!identity) {
      throw new Error('A loaded user is required to open the delete dialog.');
    }
    return {
      user_id: identity.user_id,
      email: identity.email ?? 'Unavailable',
      name: identity.name ?? undefined,
      created_at: identity.created_at ?? '',
      owned_apps_count: source.owned_apps.length,
      api_keys_count: source.api_keys.length,
      is_active: identity.is_active,
      is_omniadmin: identity.is_omniadmin,
    };
  }

  async function handleDelete(): Promise<void> {
    if (!identity || !detail || actionLockRef.current) return;
    const targetUserId = identity.user_id;
    if (ownedAppCount > 0) {
      setDeleteDialogUser(toDeleteDialogUser(detail));
      return;
    }

    actionLockRef.current = true;
    setPendingAction('delete');
    setActionError(null);
    setActionSuccess(null);
    try {
      const ok = await confirm({
        title: 'Delete user?',
        message: `Delete ${displayName}? This action cannot be undone.`,
        variant: 'danger',
        confirmLabel: 'Delete',
      });
      if (!ok || routeUserIdRef.current !== targetUserId) return;

      try {
        const result = await adminService.deleteUser(targetUserId);
        if (routeUserIdRef.current !== targetUserId) return;
        void mutate(() => Promise.resolve(result), {
          loading: 'Deleting user…',
          success: (data) => data.message,
          error: (error) => errorMessage(error, 'Failed to delete user'),
        });
        navigate('/admin/users');
      } catch (error: unknown) {
        if (error instanceof OwnedAppsError) {
          const latestDetail = await refreshDetail(targetUserId);
          if (latestDetail && routeUserIdRef.current === targetUserId) {
            setDeleteDialogUser(toDeleteDialogUser(latestDetail));
          }
        } else {
          if (routeUserIdRef.current !== targetUserId) return;
          setActionError(errorMessage(error, 'Failed to delete user'));
          void mutate(() => Promise.reject(error), {
            loading: 'Deleting user…',
            success: 'User deleted',
            error: (cause) => errorMessage(cause, 'Failed to delete user'),
          });
        }
      }
    } finally {
      actionLockRef.current = false;
      setPendingAction(null);
    }
  }

  if (visibleState.status === 'loading') {
    return (
      <div className="mx-auto max-w-5xl space-y-5">
        <Link
          to="/admin/users"
          className="inline-flex items-center gap-2 rounded text-sm font-medium text-blue-700 hover:text-blue-900 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:text-blue-300 dark:hover:text-blue-200"
        >
          <ArrowLeft className="h-4 w-4" aria-hidden="true" />
          Return to users
        </Link>
        <div className="flex items-center justify-center gap-3 py-12 text-gray-700 dark:text-slate-300" role="status">
          <span className="h-8 w-8 animate-spin rounded-full border-b-2 border-blue-600" aria-hidden="true" />
          <span>Loading user details…</span>
        </div>
      </div>
    );
  }

  if (visibleState.status === 'not-found') {
    return (
      <div className="mx-auto max-w-5xl space-y-5">
        <Link
          to="/admin/users"
          className="inline-flex items-center gap-2 rounded text-sm font-medium text-blue-700 hover:text-blue-900 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:text-blue-300 dark:hover:text-blue-200"
        >
          <ArrowLeft className="h-4 w-4" aria-hidden="true" />
          Return to users
        </Link>
        <section className="rounded-lg border border-gray-200 bg-white p-6 dark:border-slate-700 dark:bg-slate-800">
          <h1 className="text-xl font-semibold text-gray-900 dark:text-slate-100">User not found</h1>
          <p className="mt-2 text-sm text-gray-600 dark:text-slate-400">
            This user may have been removed or the address may be invalid.
          </p>
        </section>
      </div>
    );
  }

  if (visibleState.status === 'error') {
    return (
      <div className="mx-auto max-w-5xl space-y-5">
        <Link
          to="/admin/users"
          className="inline-flex items-center gap-2 rounded text-sm font-medium text-blue-700 hover:text-blue-900 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:text-blue-300 dark:hover:text-blue-200"
        >
          <ArrowLeft className="h-4 w-4" aria-hidden="true" />
          Return to users
        </Link>
        <section className="space-y-4 rounded-lg border border-gray-200 bg-white p-6 dark:border-slate-700 dark:bg-slate-800">
          <div role="alert" className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800 dark:border-red-800 dark:bg-red-900/20 dark:text-red-200">
            <h1 className="font-semibold">Unable to load user details</h1>
            <p className="mt-1">{visibleState.message}</p>
          </div>
          <button
            type="button"
            onClick={() => { void loadDetail(); }}
            className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
          >
            Try again
          </button>
        </section>
      </div>
    );
  }

  if (!detail || !identity) return null;

  const labelClass = 'text-sm text-gray-500 dark:text-slate-400';
  const valueClass = 'mt-1 break-words text-sm font-medium text-gray-900 dark:text-slate-100';
  const hasFrozenApps = detail.owned_apps.some((app) => app.is_frozen);
  const hasFrozenCollaborations = detail.collaborations.some((membership) => membership.is_frozen);

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <Link
        to="/admin/users"
        className="inline-flex items-center gap-2 rounded text-sm font-medium text-blue-700 hover:text-blue-900 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:text-blue-300 dark:hover:text-blue-200"
      >
        <ArrowLeft className="h-4 w-4" aria-hidden="true" />
        Return to users
      </Link>

      <header className="overflow-hidden rounded-2xl border border-blue-100 bg-gradient-to-br from-blue-50 via-white to-indigo-50 p-6 shadow-sm dark:border-slate-700 dark:from-slate-800 dark:via-slate-800 dark:to-indigo-950">
        <div className="flex flex-col gap-5 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex min-w-0 items-center gap-4">
            <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl bg-blue-600 text-xl font-bold text-white shadow-sm dark:bg-blue-500" aria-hidden="true">
              {(identity.name?.trim().charAt(0) || identity.email?.trim().charAt(0) || '?').toUpperCase()}
            </div>
            <div className="min-w-0">
              <p className="text-sm font-semibold uppercase tracking-wide text-blue-700 dark:text-blue-300">Platform user</p>
              <h1 className="mt-1 break-words text-2xl font-bold text-gray-950 dark:text-white">{displayName}</h1>
              <p className="mt-1 break-all text-sm text-gray-600 dark:text-slate-300">{unavailable(identity.email)}</p>
              <p className="mt-1 text-xs text-gray-500 dark:text-slate-400">User ID {identity.user_id}</p>
            </div>
          </div>
          <div className="flex flex-wrap gap-2 sm:justify-end">
            <span className={`inline-flex items-center rounded-full border px-3 py-1.5 text-sm font-semibold ${
              identity.is_active
                ? 'border-green-200 bg-green-50 text-green-800 dark:border-green-800 dark:bg-green-900/30 dark:text-green-200'
                : 'border-red-200 bg-red-50 text-red-800 dark:border-red-800 dark:bg-red-900/30 dark:text-red-200'
            }`}>
              {identity.is_active ? 'Account active' : 'Account inactive'}
            </span>
            {identity.is_omniadmin && (
              <span className="inline-flex items-center rounded-full border border-purple-200 bg-purple-50 px-3 py-1.5 text-sm font-semibold text-purple-800 dark:border-purple-800 dark:bg-purple-900/30 dark:text-purple-200">
                Omniadmin
              </span>
            )}
          </div>
        </div>
      </header>

      <div role="status" aria-live="polite" className="sr-only">
        {pendingAction ? `${pendingAction} in progress` : actionSuccess ?? ''}
      </div>
      {actionError && <Alert type="error" title="Action failed" message={actionError} />}
      {actionSuccess && (
        <div aria-hidden="true">
          <Alert type="success" title="Action completed" message={actionSuccess} />
        </div>
      )}

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {[
          { label: 'Owned apps', value: detail.owned_apps.length, detail: 'Apps owned by this user' },
          { label: 'App memberships', value: detail.collaborations.length, detail: 'Invitations and memberships' },
          { label: 'API keys', value: detail.api_keys.length, detail: 'Keys owned by this user' },
          { label: 'System LLM calls', value: detail.usage?.call_count ?? 0, detail: `Since ${formatDate(detail.usage?.billing_period_start)}` },
        ].map((item) => (
          <div key={item.label} className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm dark:border-slate-700 dark:bg-slate-800">
            <p className="text-sm font-medium text-gray-600 dark:text-slate-400">{item.label}</p>
            <p className="mt-2 text-3xl font-bold tracking-tight text-gray-950 dark:text-white">{item.value}</p>
            <p className="mt-1 text-xs text-gray-500 dark:text-slate-400">{item.detail}</p>
          </div>
        ))}
      </div>

      {(hasFrozenApps || hasFrozenCollaborations) && (
        <Alert
          type="info"
          title="Some access is paused by plan limits"
          message="An owned app can be paused when the owner's plan allows fewer apps than they currently have. A collaboration can be paused when its app exceeds the plan's collaborator limit. Review the relevant plan limits; removing resources or changing the plan may restore access."
        />
      )}

      <SectionCard
        title="Identity and account"
        description="Account identity and sign-in information. Missing values are shown as unavailable rather than inferred."
      >
        <dl className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <div><dt className={labelClass}>User ID</dt><dd className={valueClass}>{identity.user_id}</dd></div>
          <div><dt className={labelClass}>Name</dt><dd className={valueClass}>{unavailable(identity.name)}</dd></div>
          <div><dt className={labelClass}>Email</dt><dd className={valueClass}>{unavailable(identity.email)}</dd></div>
          <div><dt className={labelClass}>Created</dt><dd className={valueClass}>{formatDate(identity.created_at)}</dd></div>
          <div><dt className={labelClass}>Authentication method</dt><dd className={valueClass}>{unavailable(identity.auth_method)}</dd></div>
          <div>
            <dt className={labelClass}>Email verification</dt>
            <dd className={valueClass}>{identity.email_verified ? 'Verified' : 'Not verified'}</dd>
          </div>
        </dl>
      </SectionCard>

      <SectionCard
        title="Platform access"
        description="This role controls platform-level administration. It is separate from the user's role in each app."
      >
        <dl className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div><dt className={labelClass}>Platform role</dt><dd className={valueClass}>{unavailable(identity.platform_role)}</dd></div>
          <div>
            <dt className={labelClass}>Effective omniadmin</dt>
            <dd className={valueClass}>{identity.is_omniadmin ? 'Yes' : 'No'}</dd>
          </div>
        </dl>
      </SectionCard>

      <SectionCard
        title={`Owned apps (${detail.owned_apps.length})`}
        description="Apps this user owns. A paused app may be unavailable because the owner's plan limit was exceeded."
      >
        {detail.owned_apps.length === 0 ? (
          <p className="text-sm text-gray-600 dark:text-slate-400">This user does not own any apps.</p>
        ) : (
          <ul className="grid grid-cols-1 gap-3 md:grid-cols-2">
            {detail.owned_apps.map((app) => (
              <li key={app.app_id} className="rounded-lg border border-gray-200 p-4 dark:border-slate-700">
                <h3 className="font-semibold text-gray-900 dark:text-slate-100">{unavailable(app.name)}</h3>
                <dl className="mt-3 grid grid-cols-2 gap-3">
                  <div><dt className={labelClass}>App ID</dt><dd className={valueClass}>{app.app_id}</dd></div>
                  <div>
                    <dt className={labelClass}>App availability</dt>
                    <dd className={valueClass}>{app.is_frozen ? 'Paused by plan limit' : 'Available'}</dd>
                  </div>
                </dl>
                {app.is_frozen && (
                  <p className="mt-3 text-xs leading-5 text-amber-800 dark:text-amber-200">
                    This app is paused because the owner's plan allows fewer apps than they currently own.
                  </p>
                )}
              </li>
            ))}
          </ul>
        )}
      </SectionCard>

      <SectionCard
        title={`App memberships (${detail.collaborations.length})`}
        description="Roles here apply only to the named app; they do not change platform access."
      >
        {detail.collaborations.length === 0 ? (
          <p className="text-sm text-gray-600 dark:text-slate-400">This user has no app collaborations.</p>
        ) : (
          <ul className="grid grid-cols-1 gap-3 md:grid-cols-2">
            {detail.collaborations.map((membership) => (
              <li key={membership.app_id} className="rounded-lg border border-gray-200 p-4 dark:border-slate-700">
                <h3 className="font-semibold text-gray-900 dark:text-slate-100">{unavailable(membership.app_name)}</h3>
                <dl className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <div><dt className={labelClass}>App ID</dt><dd className={valueClass}>{membership.app_id}</dd></div>
                  <div><dt className={labelClass}>Collaboration role</dt><dd className={valueClass}>{membership.role}</dd></div>
                  <div><dt className={labelClass}>Status</dt><dd className={valueClass}>{membership.status}</dd></div>
                  <div>
                    <dt className={labelClass}>Member access</dt>
                    <dd className={valueClass}>{membership.is_frozen ? 'Paused by app plan limit' : 'Available'}</dd>
                  </div>
                  <div><dt className={labelClass}>Invited</dt><dd className={valueClass}>{formatDate(membership.invited_at)}</dd></div>
                  <div><dt className={labelClass}>Accepted</dt><dd className={valueClass}>{formatDate(membership.accepted_at)}</dd></div>
                </dl>
                {membership.is_frozen && (
                  <p className="mt-3 text-xs leading-5 text-amber-800 dark:text-amber-200">
                    This member's access is paused because the app has exceeded its plan's collaborator limit.
                  </p>
                )}
              </li>
            ))}
          </ul>
        )}
      </SectionCard>

      <SectionCard
        title={`API keys (${detail.api_keys.length})`}
        description="Keys are shown as metadata only. The secret value is never returned or displayed here."
      >
        {detail.api_keys.length === 0 ? (
          <p className="text-sm text-gray-600 dark:text-slate-400">This user has no API keys.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200 dark:divide-slate-700">
              <thead className="bg-gray-50 dark:bg-slate-700">
                <tr>
                  {['Name', 'Key ID', 'App', 'Status', 'Created', 'Last used'].map((heading) => (
                    <th key={heading} scope="col" className="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-gray-600 dark:text-slate-300">{heading}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200 dark:divide-slate-700">
                {detail.api_keys.map((key) => (
                  <tr key={key.key_id}>
                    <td className="px-3 py-3 text-sm text-gray-900 dark:text-slate-100">{key.name}</td>
                    <td className="px-3 py-3 text-sm text-gray-700 dark:text-slate-300">{key.key_id}</td>
                    <td className="px-3 py-3 text-sm text-gray-700 dark:text-slate-300">{unavailable(key.app_name)} (ID {key.app_id})</td>
                    <td className="px-3 py-3 text-sm text-gray-700 dark:text-slate-300">{key.is_active ? 'Active' : 'Inactive'}</td>
                    <td className="px-3 py-3 text-sm text-gray-700 dark:text-slate-300">{formatDate(key.created_at)}</td>
                    <td className="px-3 py-3 text-sm text-gray-700 dark:text-slate-300">{key.last_used_at ? formatDate(key.last_used_at) : 'Never used'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </SectionCard>

      <SectionCard
        title="Usage"
        description="This is only the system LLM-call count recorded directly for this user. It does not include app-wide, API-key, or marketplace activity."
      >
        <p className="text-2xl font-semibold text-gray-900 dark:text-slate-100">
          {detail.usage?.call_count ?? 0}
          <span className="ml-2 text-sm font-normal text-gray-600 dark:text-slate-400">system LLM calls</span>
        </p>
        <p className="mt-1 text-sm text-gray-600 dark:text-slate-400">
          System LLM calls recorded for this user during the billing period starting {formatDate(detail.usage?.billing_period_start)}.
        </p>
      </SectionCard>

      <SectionCard
        title="Edit account"
        description="Administrative actions are performed here so the account and its relationships can be reviewed before making changes."
      >
        {actionsRestricted ? (
          <p className="text-sm text-gray-700 dark:text-slate-300" role="status">
            {isSelf ? 'Actions are unavailable for your own account.' : 'This protected omniadmin account cannot be changed here.'}
          </p>
        ) : (
          <div className="space-y-6">
            <section className="rounded-xl bg-gray-50 p-4 dark:bg-slate-900/50" aria-labelledby="platform-role-actions">
              <h3 id="platform-role-actions" className="font-semibold text-gray-900 dark:text-slate-100">Platform role</h3>
              <p className="mt-1 text-sm leading-5 text-gray-600 dark:text-slate-400">
                Viewer: read-only access. Editor: can create and edit resources. Admin: can manage platform users and settings. These settings do not change app membership roles.
              </p>
              <div className="mt-3 flex flex-wrap gap-2">
              {(['viewer', 'editor', 'admin'] as const).map((role) => (
                <button
                  key={role}
                  type="button"
                  onClick={() => { void handleSetPlatformRole(role); }}
                  disabled={pendingAction !== null || identity.platform_role === role}
                  className="inline-flex items-center gap-2 rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm font-medium capitalize text-gray-800 hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:cursor-not-allowed disabled:opacity-50 dark:border-slate-600 dark:bg-slate-700 dark:text-slate-100 dark:hover:bg-slate-600"
                >
                  <Shield className="h-4 w-4" aria-hidden="true" />
                  {pendingAction === 'Updating role' ? 'Updating…' : `Set ${role}`}
                </button>
              ))}
              </div>
            </section>

            <section className="rounded-xl bg-gray-50 p-4 dark:bg-slate-900/50" aria-labelledby="account-status-actions">
              <h3 id="account-status-actions" className="font-semibold text-gray-900 dark:text-slate-100">Sign-in access</h3>
              <p className="mt-1 text-sm leading-5 text-gray-600 dark:text-slate-400">
                Deactivating blocks the account from signing in. Reactivate it to restore sign-in access.
              </p>
              <div className="mt-3 flex flex-wrap gap-2">
              {identity.is_active ? (
                <button
                  type="button"
                  onClick={() => { void handleDeactivate(); }}
                  disabled={pendingAction !== null}
                  className="inline-flex items-center gap-2 rounded-lg border border-amber-300 px-3 py-2 text-sm font-medium text-amber-800 hover:bg-amber-50 focus:outline-none focus:ring-2 focus:ring-amber-500 disabled:cursor-not-allowed disabled:opacity-50 dark:border-amber-700 dark:text-amber-200 dark:hover:bg-amber-900/30"
                >
                  <Ban className="h-4 w-4" aria-hidden="true" />
                  {pendingAction === 'Deactivating user' ? 'Deactivating…' : 'Deactivate'}
                </button>
              ) : (
                <button
                  type="button"
                  onClick={() => { void handleActivate(); }}
                  disabled={pendingAction !== null}
                  className="inline-flex items-center gap-2 rounded-lg border border-green-300 px-3 py-2 text-sm font-medium text-green-800 hover:bg-green-50 focus:outline-none focus:ring-2 focus:ring-green-500 disabled:cursor-not-allowed disabled:opacity-50 dark:border-green-700 dark:text-green-200 dark:hover:bg-green-900/30"
                >
                  <UserCheck className="h-4 w-4" aria-hidden="true" />
                  {pendingAction === 'Activating user' ? 'Activating…' : 'Activate'}
                </button>
              )}
                </div>
              </section>

              {isLocalMode && identity.auth_method === 'local' && (
                <section className="rounded-xl bg-gray-50 p-4 dark:bg-slate-900/50" aria-labelledby="password-reset-actions">
                  <h3 id="password-reset-actions" className="font-semibold text-gray-900 dark:text-slate-100">Password assistance</h3>
                  <p className="mt-1 text-sm leading-5 text-gray-600 dark:text-slate-400">
                    Generate a one-time link for this local account to set a new password. The link is shown once.
                  </p>
                  <button
                    type="button"
                    onClick={() => { void handleResetLink(); }}
                    disabled={pendingAction !== null}
                    className="mt-3 inline-flex items-center gap-2 rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm font-medium text-gray-800 hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:cursor-not-allowed disabled:opacity-50 dark:border-slate-600 dark:bg-slate-700 dark:text-slate-100 dark:hover:bg-slate-600"
                  >
                    <Link2 className="h-4 w-4" aria-hidden="true" />
                    {pendingAction === 'reset-link' ? 'Generating link…' : 'Generate reset link'}
                  </button>
                </section>
              )}

              {currentUser?.is_omniadmin && (
                <section className="rounded-xl bg-gray-50 p-4 dark:bg-slate-900/50" aria-labelledby="marketplace-quota-actions">
                  <h3 id="marketplace-quota-actions" className="font-semibold text-gray-900 dark:text-slate-100">Marketplace quota</h3>
                  <p className="mt-1 text-sm leading-5 text-gray-600 dark:text-slate-400">
                    Reset only the user's marketplace invocation quota. This does not change the system LLM-call count shown above.
                  </p>
                <button
                  type="button"
                    onClick={() => { void handleResetQuota(); }}
                  disabled={pendingAction !== null}
                  className="inline-flex items-center gap-2 rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm font-medium text-gray-800 hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:cursor-not-allowed disabled:opacity-50 dark:border-slate-600 dark:bg-slate-700 dark:text-slate-100 dark:hover:bg-slate-600"
                >
                    <RefreshCcw className="h-4 w-4" aria-hidden="true" />
                    {pendingAction === 'Resetting marketplace quota' ? 'Resetting quota…' : 'Reset marketplace quota'}
                </button>
                </section>
              )}

              <section className="rounded-xl border border-red-200 bg-red-50/70 p-4 dark:border-red-900 dark:bg-red-950/20" aria-labelledby="delete-user-action">
                <h3 id="delete-user-action" className="font-semibold text-red-900 dark:text-red-200">Delete account</h3>
                <p className="mt-1 text-sm leading-5 text-red-800 dark:text-red-300">
                  Permanently remove this account. If the user owns apps, you will be asked to transfer them or confirm deleting them too.
                </p>
              <button
                type="button"
                onClick={() => { void handleDelete(); }}
                disabled={pendingAction !== null}
                className="inline-flex items-center gap-2 rounded-lg border border-red-300 px-3 py-2 text-sm font-medium text-red-800 hover:bg-red-50 focus:outline-none focus:ring-2 focus:ring-red-500 disabled:cursor-not-allowed disabled:opacity-50 dark:border-red-700 dark:text-red-200 dark:hover:bg-red-900/30"
              >
                <Trash2 className="h-4 w-4" aria-hidden="true" />
                {pendingAction === 'delete' ? 'Deleting…' : 'Delete user'}
              </button>
              {ownedAppCount > 0 && <p className="mt-2 text-sm font-medium text-red-800 dark:text-red-300">This user currently owns {ownedAppCount} app{ownedAppCount === 1 ? '' : 's'}.</p>}
            </section>
            {pendingAction && <p className="text-sm text-gray-600 dark:text-slate-400">{pendingAction}…</p>}
          </div>
        )}
      </SectionCard>

      {resetLinkState && (
        <OneTimeLinkModal
          isOpen
          onClose={() => setResetLinkState(null)}
          token={resetLinkState.token}
          expiresAt={resetLinkState.expiresAt}
          title="Password reset link"
        />
      )}
      {deleteDialogUser && (
        <DeleteUserDialog
          isOpen
          targetUser={deleteDialogUser}
          onClose={() => setDeleteDialogUser(null)}
          onDeleted={() => {
            setDeleteDialogUser(null);
            navigate('/admin/users');
          }}
        />
      )}
    </div>
  );
}

export default UserDetailPage;
