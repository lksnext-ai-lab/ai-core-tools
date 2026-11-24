import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { ReactNode, SubmitEvent } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
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
import Badge from '../../components/ui/Badge';
import ButtonApp from '../../components/ui/ButtonApp';
import ButtonLink from '../../components/ui/ButtonLink';
import CardApp from '../../components/ui/CardApp';
import Modal from '../../components/ui/Modal';
import { Title } from '../../components/ui/Title';
import { MetricsDashboard } from '../../components/metrics/MetricsDashboard';
import DeleteUserDialog from '../../components/admin/DeleteUserDialog';
import OneTimeLinkModal from '../../components/ui/OneTimeLinkModal';
import { useConfirm } from '../../contexts/ConfirmContext';
import { useDeploymentMode } from '../../contexts/DeploymentModeContext';
import { useUser } from '../../contexts/UserContext';
import { errorMessage } from '../../constants/messages';
import { useApiMutation } from '../../hooks/useApiMutation';
import { FormSelect } from '../../components/ui/FormField';
import { LoadingState } from '../../components/ui/LoadingState';
import { ApiError } from '../../services/api';
import { adminService, OwnedAppsError } from '../../services/admin';
import type { AdminAppOption, AppAccessRole, User, UserDetail } from '../../services/admin';
import { metricsApi } from '../../services/metrics';
import type { BreakdownDimension } from '../../types/metrics';

type DetailState =
  | { readonly userId: number | null; readonly status: 'loading' }
  | { readonly userId: number | null; readonly status: 'not-found' }
  | { readonly userId: number | null; readonly status: 'error'; readonly message: string }
  | { readonly userId: number; readonly status: 'success'; readonly detail: UserDetail };

interface ResetLinkState {
  readonly token: string;
  readonly expiresAt: string;
}

const appAccessRoles: AppAccessRole[] = ['administrator', 'editor', 'viewer'];
const appMetricsDimensions: BreakdownDimension[] = ['agent', 'model', 'channel', 'user', 'provider'];

function isAppAccessRole(role: string): role is AppAccessRole {
  return role === 'administrator' || role === 'editor' || role === 'viewer';
}

function getAllowedAppRoles(platformRole: string | null | undefined): AppAccessRole[] {
  return platformRole === 'viewer' ? ['viewer'] : appAccessRoles;
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

function appLabel(appName: string | null, appId: number): string {
  return appName || `app ${appId}`;
}

function AdminAppMetricsModal({
  appId,
  appName,
  onClose,
}: {
  readonly appId: number;
  readonly appName: string;
  readonly onClose: () => void;
}) {
  const api = useMemo(() => metricsApi.adminApp(appId), [appId]);
  return (
    <Modal isOpen onClose={onClose} title={`Metrics · ${appName}`} size="xlarge">
      <MetricsDashboard
        api={api}
        dimensions={appMetricsDimensions}
        title={`App ${appId} metrics`}
        description="Read-only usage, performance and reliability metrics for this app."
      />
    </Modal>
  );
}

function SectionCard({ title, description, children }: SectionCardProps) {
  return (
    <section aria-label={title}>
      <CardApp className="space-y-4">
        <div className="space-y-1">
          <h2 className="font-display text-xl font-normal text-ink dark:text-ink-dark">{title}</h2>
          {description && <p className="text-sm leading-6 text-fg-secondary dark:text-fg-secondary-dark">{description}</p>}
        </div>
        {children}
      </CardApp>
    </section>
  );
}

const labelClass = 'text-xs font-medium uppercase tracking-wide text-fg-tertiary dark:text-fg-tertiary-dark';
const valueClass = 'mt-1 break-words text-sm font-medium text-fg dark:text-fg-dark';

type DetailIdentity = UserDetail['identity'];
type DetailFallbackState = Exclude<DetailState, { readonly status: 'success' }>;

function BackToUsersLink() {
  return (
    <ButtonLink
      label="Return to users"
      to="/admin/users"
      variant="muted"
      size="small"
      icon={<ArrowLeft className="h-4 w-4" aria-hidden="true" />}
    />
  );
}

function DetailFallback({ state, onRetry }: { readonly state: DetailFallbackState; readonly onRetry: () => void }) {
  if (state.status === 'loading') {
    return (
      <div className="mx-auto max-w-5xl space-y-5">
        <BackToUsersLink />
        <LoadingState variant="page" message="Loading user details…" />
      </div>
    );
  }

  if (state.status === 'not-found') {
    return (
      <div className="mx-auto max-w-5xl space-y-5">
        <BackToUsersLink />
        <CardApp className="space-y-2">
          <h1 className="font-display text-xl font-normal text-ink dark:text-ink-dark">User not found</h1>
          <p className="text-sm text-fg-secondary dark:text-fg-secondary-dark">
            This user may have been removed or the address may be invalid.
          </p>
        </CardApp>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-5xl space-y-5">
      <BackToUsersLink />
      <CardApp>
        <Alert type="error" title="Unable to load user details" message={state.message} />
        <ButtonApp type="button" onClick={onRetry} label="Try again" variant="secondary" size="small" className="mt-4" />
      </CardApp>
    </div>
  );
}

function OwnedAppsSection({
  apps,
  onOpenMetrics,
}: {
  readonly apps: UserDetail['owned_apps'];
  readonly onOpenMetrics: (appId: number, appName: string | null) => void;
}) {
  return (
    <SectionCard
      title={`Owned apps (${apps.length})`}
      description="Apps this user owns. A paused app may be unavailable because the owner's plan limit was exceeded."
    >
      {apps.length === 0 ? (
        <p className="text-sm text-fg-secondary dark:text-fg-secondary-dark">This user does not own any apps.</p>
      ) : (
        <ul className="grid grid-cols-1 gap-3 md:grid-cols-2">
          {apps.map((app) => (
            <li key={app.app_id} className="group relative cursor-pointer rounded-md border border-line bg-surface p-4 transition-colors hover:border-accent hover:bg-surface-hover dark:border-line-dark dark:bg-surface-dark dark:hover:bg-surface-hover-dark">
              <button
                type="button"
                onClick={() => onOpenMetrics(app.app_id, app.name)}
                aria-label={`View metrics for ${appLabel(app.name, app.app_id)}`}
                className="absolute inset-0 z-10 cursor-pointer rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus dark:focus-visible:ring-focus-dark focus-visible:ring-inset"
              />
              <h3 className="font-display text-base font-medium text-ink group-hover:underline dark:text-ink-dark">{unavailable(app.name)}</h3>
              <dl className="mt-3 grid grid-cols-2 gap-3">
                <div><dt className={labelClass}>App ID</dt><dd className={valueClass}>{app.app_id}</dd></div>
                <div>
                  <dt className={labelClass}>App availability</dt>
                  <dd className="mt-1"><Badge label={app.is_frozen ? 'Paused by plan limit' : 'Available'} variant={app.is_frozen ? 'warning' : 'success'} /></dd>
                </div>
              </dl>
              {app.is_frozen && (
                <p className="mt-3 text-xs leading-5 text-bronze-strong dark:text-bronze-strong-dark">
                  This app is paused because the owner's plan allows fewer apps than they currently own.
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
    </SectionCard>
  );
}

interface AppMembershipsSectionProps {
  readonly identity: DetailIdentity;
  readonly onOpenMetrics: (appId: number, appName: string | null) => void;
  readonly collaborations: UserDetail['collaborations'];
  readonly actionsRestricted: boolean;
  readonly pendingAction: string | null;
  readonly adminAppsError: string | null;
  readonly adminAppsCount: number;
  readonly selectableApps: AdminAppOption[];
  readonly allowedAppRoles: AppAccessRole[];
  readonly selectedAppId: string;
  readonly selectedGrantRole: AppAccessRole;
  readonly onSelectedAppIdChange: (appId: string) => void;
  readonly onSelectedAppRoleChange: (role: AppAccessRole) => void;
  readonly onGrantAccess: (event: SubmitEvent<HTMLFormElement>) => Promise<void>;
  readonly onSetAppRole: (appId: number, role: AppAccessRole) => Promise<void>;
  readonly onRemoveAppAccess: (appId: number, appName: string | null) => Promise<void>;
}

function AppMembershipsSection({
  identity,
  onOpenMetrics,
  collaborations,
  actionsRestricted,
  pendingAction,
  adminAppsError,
  adminAppsCount,
  selectableApps,
  allowedAppRoles,
  selectedAppId,
  selectedGrantRole,
  onSelectedAppIdChange,
  onSelectedAppRoleChange,
  onGrantAccess,
  onSetAppRole,
  onRemoveAppAccess,
}: AppMembershipsSectionProps) {
  return (
    <SectionCard
      title={`App memberships (${collaborations.length})`}
      description="Roles here apply only to the named app; they do not change platform access."
    >
      {actionsRestricted ? (
        <output className="mb-4 block text-sm text-fg-secondary dark:text-fg-secondary-dark">
          App access cannot be changed for your own or a protected omniadmin account.
        </output>
      ) : (
        <>
          {identity.platform_role === 'viewer' && (
            <Alert
              type="warning"
              title="Viewer platform role"
              message="This user has the Viewer platform role, so only Viewer app access can be granted. Change their platform role to Editor or Admin first to assign Editor or Administrator app access."
              className="mb-4"
            />
          )}
          <form onSubmit={(event) => { void onGrantAccess(event); }} className="mb-5 flex flex-wrap items-end gap-3 rounded-md bg-canvas-alt p-4 dark:bg-canvas-alt-dark">
            <FormSelect
              label="App"
              id="grant-app-access-app"
              value={selectedAppId}
              onChange={(event) => onSelectedAppIdChange(event.target.value)}
              disabled={pendingAction !== null || selectableApps.length === 0}
              className="min-w-48 flex-1"
              options={[
                { value: '', label: 'Select an app' },
                ...selectableApps.map((app) => {
                  const appName = app.name || `App ${app.app_id}`;
                  return {
                    value: app.app_id,
                    label: `${appName} (ID ${app.app_id})`,
                  };
                }),
              ]}
            />
            <FormSelect
              label="Role"
              id="grant-app-access-role"
              value={selectedGrantRole}
              onChange={(event) => {
                if (isAppAccessRole(event.target.value)) onSelectedAppRoleChange(event.target.value);
              }}
              disabled={pendingAction !== null}
              options={allowedAppRoles.map((role) => ({ value: role, label: role }))}
            />
            <ButtonApp
              type="submit"
              label="Grant access"
              variant="primary"
              size="small"
              disabled={pendingAction !== null || selectedAppId === ''}
            />
            {adminAppsError && <p className="w-full text-sm text-error dark:text-error-dark" role="alert">{adminAppsError}</p>}
            {!adminAppsError && adminAppsCount === 0 && (
              <p className="w-full text-sm text-fg-secondary dark:text-fg-secondary-dark">No apps are available.</p>
            )}
            {!adminAppsError && adminAppsCount > 0 && selectableApps.length === 0 && (
              <p className="w-full text-sm text-fg-secondary dark:text-fg-secondary-dark">This user already owns or has access to every app.</p>
            )}
          </form>
        </>
      )}
      {collaborations.length === 0 ? (
        <p className="text-sm text-fg-secondary dark:text-fg-secondary-dark">This user has no app collaborations.</p>
      ) : (
        <ul className="grid grid-cols-1 gap-3 md:grid-cols-2">
          {collaborations.map((membership) => (
            <li key={membership.collaboration_id} className="group relative cursor-pointer rounded-md border border-line bg-surface p-4 transition-colors hover:border-accent hover:bg-surface-hover dark:border-line-dark dark:bg-surface-dark dark:hover:bg-surface-hover-dark">
              <button
                type="button"
                onClick={() => onOpenMetrics(membership.app_id, membership.app_name)}
                aria-label={`View metrics for ${appLabel(membership.app_name, membership.app_id)}`}
                className="absolute inset-0 z-10 cursor-pointer rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus dark:focus-visible:ring-focus-dark focus-visible:ring-inset"
              />
              <h3 className="font-display text-base font-medium text-ink group-hover:underline dark:text-ink-dark">{unavailable(membership.app_name)}</h3>
              <dl className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
                <div><dt className={labelClass}>App ID</dt><dd className={valueClass}>{membership.app_id}</dd></div>
                <div><dt className={labelClass}>Collaboration role</dt><dd className={valueClass}>{membership.role}</dd></div>
                <div><dt className={labelClass}>Status</dt><dd className="mt-1"><Badge label={membership.status} variant={membership.status === 'accepted' ? 'success' : 'warning'} /></dd></div>
                <div>
                  <dt className={labelClass}>Member access</dt>
                  <dd className="mt-1"><Badge label={membership.is_frozen ? 'Paused by app plan limit' : 'Available'} variant={membership.is_frozen ? 'warning' : 'success'} /></dd>
                </div>
                <div><dt className={labelClass}>Invited</dt><dd className={valueClass}>{formatDate(membership.invited_at)}</dd></div>
                <div><dt className={labelClass}>Accepted</dt><dd className={valueClass}>{formatDate(membership.accepted_at)}</dd></div>
              </dl>
              {membership.is_frozen && (
                <p className="mt-3 text-xs leading-5 text-bronze-strong dark:text-bronze-strong-dark">
                  This member's access is paused because the app has exceeded its plan's collaborator limit.
                </p>
              )}
              {!actionsRestricted && (
                <div className="relative z-20 mt-4 flex flex-wrap items-center gap-2 border-t border-line pt-3 dark:border-line-dark">
                  <label className="text-sm text-fg-secondary dark:text-fg-secondary-dark">
                    <span className="mr-2">Set role</span>
                    <select
                      aria-label={`Role for ${appLabel(membership.app_name, membership.app_id)}`}
                      value={membership.role}
                      onChange={(event) => {
                        if (isAppAccessRole(event.target.value) && allowedAppRoles.includes(event.target.value)) {
                          void onSetAppRole(membership.app_id, event.target.value);
                        }
                      }}
                      disabled={pendingAction !== null}
                      className="ml-2 rounded-md border border-line-strong bg-surface px-2 py-1 text-sm text-fg focus:outline-none focus-visible:ring-2 focus-visible:ring-focus dark:border-line-strong-dark dark:bg-surface-dark dark:text-fg-dark dark:focus-visible:ring-focus-dark"
                    >
                      {(!isAppAccessRole(membership.role) || !allowedAppRoles.includes(membership.role)) && (
                        <option value={membership.role}>{membership.role} (legacy)</option>
                      )}
                      {allowedAppRoles.map((role) => (
                        <option key={role} value={role}>{role}</option>
                      ))}
                    </select>
                  </label>
                  <ButtonApp
                    type="button"
                    onClick={() => { void onRemoveAppAccess(membership.app_id, membership.app_name); }}
                    label="Remove access"
                    variant="danger"
                    size="small"
                    disabled={pendingAction !== null}
                  />
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </SectionCard>
  );
}

interface ApiKeysSectionProps {
  readonly apiKeys: UserDetail['api_keys'];
  readonly actionsRestricted: boolean;
  readonly pendingAction: string | null;
  readonly onSetAPIKeyStatus: (keyId: number, keyName: string, isActive: boolean) => Promise<void>;
}

function ApiKeysSection({ apiKeys, actionsRestricted, pendingAction, onSetAPIKeyStatus }: ApiKeysSectionProps) {
  return (
    <SectionCard
      title={`API keys (${apiKeys.length})`}
      description="Keys are shown as metadata only. The secret value is never returned or displayed here."
    >
      {apiKeys.length === 0 ? (
        <p className="text-sm text-fg-secondary dark:text-fg-secondary-dark">This user has no API keys.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200 dark:divide-slate-700">
            <thead className="bg-canvas-alt dark:bg-canvas-alt-dark">
              <tr>
                {['Name', 'Key ID', 'App', 'Status', 'Created', 'Last used', 'Actions'].map((heading) => (
                  <th key={heading} scope="col" className="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-fg-tertiary dark:text-fg-tertiary-dark">{heading}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-line dark:divide-line-dark">
              {apiKeys.map((key) => (
                <tr key={key.key_id}>
                  <td className="px-3 py-3 text-sm font-medium text-fg dark:text-fg-dark">{key.name}</td>
                  <td className="px-3 py-3 text-sm text-fg-secondary dark:text-fg-secondary-dark">{key.key_id}</td>
                  <td className="px-3 py-3 text-sm text-fg-secondary dark:text-fg-secondary-dark">{unavailable(key.app_name)} (ID {key.app_id})</td>
                  <td className="px-3 py-3 text-sm"><Badge label={key.is_active ? 'Active' : 'Inactive'} variant={key.is_active ? 'success' : 'default'} /></td>
                  <td className="px-3 py-3 text-sm text-fg-secondary dark:text-fg-secondary-dark">{formatDate(key.created_at)}</td>
                  <td className="px-3 py-3 text-sm text-fg-secondary dark:text-fg-secondary-dark">{key.last_used_at ? formatDate(key.last_used_at) : 'Never used'}</td>
                  <td className="px-3 py-3 text-sm">
                    {actionsRestricted ? (
                      <span className="text-fg-tertiary dark:text-fg-tertiary-dark">Unavailable</span>
                    ) : (
                      <ButtonApp
                        type="button"
                        onClick={() => { void onSetAPIKeyStatus(key.key_id, key.name, !key.is_active); }}
                        disabled={pendingAction !== null}
                        ariaLabel={`${key.is_active ? 'Deactivate' : 'Reactivate'} API key ${key.name}`}
                        label={key.is_active ? 'Deactivate' : 'Reactivate'}
                        variant={key.is_active ? 'danger' : 'secondary'}
                        size="small"
                      />
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </SectionCard>
  );
}

interface EditAccountSectionProps {
  readonly identity: DetailIdentity;
  readonly isSelf: boolean;
  readonly actionsRestricted: boolean;
  readonly isLocalMode: boolean;
  readonly canResetQuota: boolean;
  readonly ownedAppCount: number;
  readonly pendingAction: string | null;
  readonly onSetPlatformRole: (role: 'viewer' | 'editor' | 'admin') => Promise<void>;
  readonly onDeactivate: () => Promise<void>;
  readonly onActivate: () => Promise<void>;
  readonly onResetLink: () => Promise<void>;
  readonly onResetQuota: () => Promise<void>;
  readonly onDelete: () => Promise<void>;
}

function PlatformRoleControl({
  identity,
  pendingAction,
  onSetPlatformRole,
}: Pick<EditAccountSectionProps, 'identity' | 'pendingAction' | 'onSetPlatformRole'>) {
  return (
    <section aria-labelledby="platform-role-actions">
      <CardApp variant="canvas" className="space-y-3">
        <h3 id="platform-role-actions" className="font-display text-base font-medium text-fg dark:text-fg-dark">Platform role</h3>
        <p className="text-sm text-fg-secondary dark:text-fg-secondary-dark">
          Current role: <span className="font-medium capitalize text-fg dark:text-fg-dark">{unavailable(identity.platform_role)}</span>
        </p>
        <p className="text-sm leading-5 text-fg-secondary dark:text-fg-secondary-dark">
          Viewer: read-only access. Editor: can create and edit resources. Admin: can manage platform users and settings. These settings do not change app membership roles.
        </p>
        <div className="flex flex-wrap gap-2">
          {(['viewer', 'editor', 'admin'] as const).map((role) => (
            <ButtonApp
              key={role}
              type="button"
              onClick={() => { void onSetPlatformRole(role); }}
              disabled={pendingAction !== null || identity.platform_role === role}
              label={pendingAction === 'Updating role' ? 'Updating…' : `Set ${role}`}
              variant="secondary"
              size="small"
              icon={<Shield className="h-4 w-4" aria-hidden="true" />}
              className="capitalize"
            />
          ))}
        </div>
      </CardApp>
    </section>
  );
}

function SignInAccessControl({
  identity,
  pendingAction,
  onDeactivate,
  onActivate,
}: Pick<EditAccountSectionProps, 'identity' | 'pendingAction' | 'onDeactivate' | 'onActivate'>) {
  return (
    <section aria-labelledby="account-status-actions">
      <CardApp variant="canvas" className="space-y-3">
        <h3 id="account-status-actions" className="font-display text-base font-medium text-fg dark:text-fg-dark">Sign-in access</h3>
        <p className="text-sm leading-5 text-fg-secondary dark:text-fg-secondary-dark">
          Deactivating blocks the account from signing in. Reactivate it to restore sign-in access.
        </p>
        <div className="flex flex-wrap gap-2">
        {identity.is_active ? (
          <ButtonApp
            type="button"
            onClick={() => { void onDeactivate(); }}
            disabled={pendingAction !== null}
            label={pendingAction === 'Deactivating user' ? 'Deactivating…' : 'Deactivate'}
            variant="danger"
            size="small"
            icon={<Ban className="h-4 w-4" aria-hidden="true" />}
          />
        ) : (
          <ButtonApp
            type="button"
            onClick={() => { void onActivate(); }}
            disabled={pendingAction !== null}
            label={pendingAction === 'Activating user' ? 'Activating…' : 'Activate'}
            variant="primary"
            size="small"
            icon={<UserCheck className="h-4 w-4" aria-hidden="true" />}
          />
        )}
        </div>
      </CardApp>
    </section>
  );
}

function PasswordAssistanceControl({
  pendingAction,
  onResetLink,
}: Pick<EditAccountSectionProps, 'pendingAction' | 'onResetLink'>) {
  return (
    <section aria-labelledby="password-reset-actions">
      <CardApp variant="canvas" className="space-y-3">
        <h3 id="password-reset-actions" className="font-display text-base font-medium text-fg dark:text-fg-dark">Password assistance</h3>
        <p className="text-sm leading-5 text-fg-secondary dark:text-fg-secondary-dark">
          Generate a one-time link for this local account to set a new password. The link is shown once.
        </p>
        <ButtonApp
          type="button"
          onClick={() => { void onResetLink(); }}
          disabled={pendingAction !== null}
          label={pendingAction === 'reset-link' ? 'Generating link…' : 'Generate reset link'}
          variant="secondary"
          size="small"
          icon={<Link2 className="h-4 w-4" aria-hidden="true" />}
        />
      </CardApp>
    </section>
  );
}

function MarketplaceQuotaControl({
  pendingAction,
  onResetQuota,
}: Pick<EditAccountSectionProps, 'pendingAction' | 'onResetQuota'>) {
  return (
    <section aria-labelledby="marketplace-quota-actions">
      <CardApp variant="canvas" className="space-y-3">
        <h3 id="marketplace-quota-actions" className="font-display text-base font-medium text-fg dark:text-fg-dark">Marketplace quota</h3>
        <p className="text-sm leading-5 text-fg-secondary dark:text-fg-secondary-dark">
          Reset only the user's marketplace invocation quota. This does not change the system LLM-call count shown above.
        </p>
        <ButtonApp
          type="button"
          onClick={() => { void onResetQuota(); }}
          disabled={pendingAction !== null}
          label={pendingAction === 'Resetting marketplace quota' ? 'Resetting quota…' : 'Reset marketplace quota'}
          variant="secondary"
          size="small"
          icon={<RefreshCcw className="h-4 w-4" aria-hidden="true" />}
        />
      </CardApp>
    </section>
  );
}

function DeleteAccountControl({
  ownedAppCount,
  pendingAction,
  onDelete,
}: Pick<EditAccountSectionProps, 'ownedAppCount' | 'pendingAction' | 'onDelete'>) {
  return (
    <section aria-labelledby="delete-user-action">
      <CardApp variant="white" className="space-y-3 border-error dark:border-error-dark">
        <h3 id="delete-user-action" className="font-display text-base font-medium text-error dark:text-error-dark">Delete account</h3>
        <p className="text-sm leading-5 text-fg-secondary dark:text-fg-secondary-dark">
          Permanently remove this account. If the user owns apps, you will be asked to transfer them or confirm deleting them too.
        </p>
        <ButtonApp
          type="button"
          onClick={() => { void onDelete(); }}
          disabled={pendingAction !== null}
          label={pendingAction === 'delete' ? 'Deleting…' : 'Delete user'}
          variant="dangerSolid"
          size="small"
          icon={<Trash2 className="h-4 w-4" aria-hidden="true" />}
        />
        {ownedAppCount > 0 && <p className="text-sm font-medium text-error dark:text-error-dark">This user currently owns {ownedAppCount} app{ownedAppCount === 1 ? '' : 's'}.</p>}
      </CardApp>
    </section>
  );
}

function EditAccountSection({
  identity,
  isSelf,
  actionsRestricted,
  isLocalMode,
  canResetQuota,
  ownedAppCount,
  pendingAction,
  onSetPlatformRole,
  onDeactivate,
  onActivate,
  onResetLink,
  onResetQuota,
  onDelete,
}: EditAccountSectionProps) {
  return (
    <SectionCard
      title="Edit account"
      description="Administrative actions are performed here so the account and its relationships can be reviewed before making changes."
    >
      {actionsRestricted ? (
        <output className="block text-sm text-fg-secondary dark:text-fg-secondary-dark">
          {isSelf ? 'Actions are unavailable for your own account.' : 'This protected omniadmin account cannot be changed here.'}
        </output>
      ) : (
        <div className="space-y-6">
          <PlatformRoleControl identity={identity} pendingAction={pendingAction} onSetPlatformRole={onSetPlatformRole} />
          <SignInAccessControl identity={identity} pendingAction={pendingAction} onDeactivate={onDeactivate} onActivate={onActivate} />
          {isLocalMode && identity.auth_method === 'local' && (
            <PasswordAssistanceControl pendingAction={pendingAction} onResetLink={onResetLink} />
          )}
          {canResetQuota && <MarketplaceQuotaControl pendingAction={pendingAction} onResetQuota={onResetQuota} />}
          <DeleteAccountControl ownedAppCount={ownedAppCount} pendingAction={pendingAction} onDelete={onDelete} />
          {pendingAction && <p className="text-sm text-fg-secondary dark:text-fg-secondary-dark">{pendingAction}…</p>}
        </div>
      )}
    </SectionCard>
  );
}

function UserHeader({ identity, displayName }: { readonly identity: DetailIdentity; readonly displayName: string }) {
  return (
    <header>
      <CardApp variant="canvas" className="overflow-hidden p-6">
        <div className="flex flex-col gap-5 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex min-w-0 items-center gap-4">
            <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-full bg-ink font-display text-xl font-medium text-ink-on dark:bg-ink-dark dark:text-ink-on-dark" aria-hidden="true">
              {(identity.name?.trim().charAt(0) || identity.email?.trim().charAt(0) || '?').toUpperCase()}
            </div>
            <div className="min-w-0">
              <p className="mb-1 text-xs font-medium uppercase tracking-wide text-fg-tertiary dark:text-fg-tertiary-dark">Platform user</p>
              <Title
                titulo={displayName}
                subtitulo={unavailable(identity.email)}
                variant="titSecundario"
                titleMarginBottom={2}
                subtitleMarginBottom={0}
              />
              <p className="mt-2 text-xs text-fg-tertiary dark:text-fg-tertiary-dark">User ID {identity.user_id}</p>
            </div>
          </div>
          <div className="flex flex-wrap gap-2 sm:justify-end">
            <Badge label={identity.is_active ? 'Account active' : 'Account inactive'} variant={identity.is_active ? 'success' : 'default'} />
            {identity.is_omniadmin && <Badge label="Omniadmin" variant="secondary" />}
          </div>
        </div>
      </CardApp>
    </header>
  );
}

function UserSummaryCards({ detail }: { readonly detail: UserDetail }) {
  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      {[
        { label: 'Owned apps', value: detail.owned_apps.length, detail: 'Apps owned by this user' },
        { label: 'App memberships', value: detail.collaborations.length, detail: 'Invitations and memberships' },
        { label: 'API keys', value: detail.api_keys.length, detail: 'Keys owned by this user' },
        { label: 'System LLM calls', value: detail.usage?.call_count ?? 0, detail: `Since ${formatDate(detail.usage?.billing_period_start)}` },
      ].map((item) => (
        <CardApp key={item.label} className="p-4">
          <p className="text-sm font-medium text-fg-secondary dark:text-fg-secondary-dark">{item.label}</p>
          <p className="mt-2 font-display text-3xl font-normal tracking-tight text-ink dark:text-ink-dark">{item.value}</p>
          <p className="mt-1 text-xs text-fg-tertiary dark:text-fg-tertiary-dark">{item.detail}</p>
        </CardApp>
      ))}
    </div>
  );
}

function IdentitySection({ identity }: { readonly identity: DetailIdentity }) {
  return (
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
  );
}

function deriveAccessState(detail: UserDetail, adminApps: AdminAppOption[], selectedAppRole: AppAccessRole) {
  const memberAppIds = new Set(
    detail.collaborations
      .filter((membership) => membership.role !== 'owner' && membership.status === 'accepted')
      .map((membership) => membership.app_id),
  );
  const ownedAppIds = new Set(detail.owned_apps.map((app) => app.app_id));
  const allowedAppRoles = getAllowedAppRoles(detail.identity.platform_role);
  return {
    hasPausedAccess: detail.owned_apps.some((app) => app.is_frozen) || detail.collaborations.some((membership) => membership.is_frozen),
    selectableApps: adminApps.filter((app) => !memberAppIds.has(app.app_id) && !ownedAppIds.has(app.app_id)),
    allowedAppRoles,
    selectedGrantRole: allowedAppRoles.includes(selectedAppRole) ? selectedAppRole : 'viewer',
  };
}

function buildDeleteDialogUser(identity: DetailIdentity, source: UserDetail): User {
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
  const [adminApps, setAdminApps] = useState<AdminAppOption[]>([]);
  const [adminAppsError, setAdminAppsError] = useState<string | null>(null);
  const [selectedAppId, setSelectedAppId] = useState('');
  const [selectedAppRole, setSelectedAppRole] = useState<AppAccessRole>('editor');
  const [selectedMetricsApp, setSelectedMetricsApp] = useState<AdminAppOption | null>(null);
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
    setSelectedMetricsApp(null);
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

  useEffect(() => {
    let active = true;
    void adminService.getApps()
      .then((apps) => {
        if (active) setAdminApps(apps);
      })
      .catch((error: unknown) => {
        if (active) setAdminAppsError(errorMessage(error, 'Unable to load apps.'));
      });
    return () => {
      active = false;
    };
  }, []);

  const openAppMetrics = useCallback((appId: number, appName: string | null) => {
    setSelectedMetricsApp({ app_id: appId, name: appName });
  }, []);

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
    const appNoun = ownedAppCount === 1 ? 'app' : 'apps';
    await runMutation(
      identity.user_id,
      'Updating role',
      () => adminService.setPlatformRole(identity.user_id, role),
      'Platform role updated.',
      {
        title: `Set role to ${roleLabels[role]}?`,
        message: downgradeWarning
          ? `${displayName} owns ${ownedAppCount} ${appNoun}. As a viewer, they will no longer be able to modify them but will retain ownership. Continue?`
          : `Change ${displayName}'s platform role to ${roleLabels[role]}?`,
        variant: downgradeWarning ? 'warning' : undefined,
        confirmLabel: 'Confirm',
      },
    );
  }

  async function handleGrantAppAccess(event: SubmitEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (!identity || !selectedAppId) return;
    const role = identity.platform_role === 'viewer' ? 'viewer' : selectedAppRole;
    await runMutation(
      identity.user_id,
      'Granting app access',
      () => adminService.setUserAppRole(identity.user_id, Number(selectedAppId), role),
      'App access granted.',
    );
  }

  async function handleSetAppRole(appId: number, role: AppAccessRole): Promise<void> {
    if (!identity) return;
    await runMutation(
      identity.user_id,
      'Updating app role',
      () => adminService.setUserAppRole(identity.user_id, appId, role),
      'App role updated.',
    );
  }

  async function handleRemoveAppAccess(appId: number, appName: string | null): Promise<void> {
    if (!identity) return;
    const targetAppLabel = appLabel(appName, appId);
    await runMutation(
      identity.user_id,
      'Removing app access',
      () => adminService.removeUserAppAccess(identity.user_id, appId),
      'App access removed.',
      {
        title: 'Remove app access?',
        message: `Remove ${displayName}'s access to ${targetAppLabel}?`,
        variant: 'warning',
        confirmLabel: 'Remove access',
      },
    );
  }

  async function handleSetAPIKeyStatus(keyId: number, keyName: string, isActive: boolean): Promise<void> {
    if (!identity) return;
    await runMutation(
      identity.user_id,
      isActive ? 'Reactivating API key' : 'Deactivating API key',
      () => adminService.setUserAPIKeyStatus(identity.user_id, keyId, isActive),
      isActive ? 'API key reactivated.' : 'API key deactivated.',
      isActive ? undefined : {
        title: 'Deactivate API key?',
        message: `Deactivate "${keyName}"? Applications using it will no longer be able to authenticate.`,
        variant: 'warning',
        confirmLabel: 'Deactivate key',
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
    return buildDeleteDialogUser(identity, source);
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

  if (visibleState.status !== 'success') {
    return <DetailFallback state={visibleState} onRetry={() => { void loadDetail(); }} />;
  }

  if (!detail || !identity) return null;

  const access = deriveAccessState(detail, adminApps, selectedAppRole);
  const { allowedAppRoles, selectedGrantRole } = access;

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <BackToUsersLink />

      <UserHeader identity={identity} displayName={displayName} />

      <div role="status" aria-live="polite" className="sr-only">
        {pendingAction ? `${pendingAction} in progress` : actionSuccess ?? ''}
      </div>
      {actionError && <Alert type="error" title="Action failed" message={actionError} />}
      {actionSuccess && (
        <div aria-hidden="true">
          <Alert type="success" title="Action completed" message={actionSuccess} />
        </div>
      )}

      <UserSummaryCards detail={detail} />

      {access.hasPausedAccess && (
        <Alert
          type="info"
          title="Some access is paused by plan limits"
          message="An owned app can be paused when the owner's plan allows fewer apps than they currently have. A collaboration can be paused when its app exceeds the plan's collaborator limit. Review the relevant plan limits; removing resources or changing the plan may restore access."
        />
      )}

      <IdentitySection identity={identity} />

      <OwnedAppsSection apps={detail.owned_apps} onOpenMetrics={openAppMetrics} />

      <AppMembershipsSection
        identity={identity}
        onOpenMetrics={openAppMetrics}
        collaborations={detail.collaborations}
        actionsRestricted={actionsRestricted}
        pendingAction={pendingAction}
        adminAppsError={adminAppsError}
        adminAppsCount={adminApps.length}
        selectableApps={access.selectableApps}
        allowedAppRoles={allowedAppRoles}
        selectedAppId={selectedAppId}
        selectedGrantRole={selectedGrantRole}
        onSelectedAppIdChange={setSelectedAppId}
        onSelectedAppRoleChange={setSelectedAppRole}
        onGrantAccess={handleGrantAppAccess}
        onSetAppRole={handleSetAppRole}
        onRemoveAppAccess={handleRemoveAppAccess}
      />

      <ApiKeysSection
        apiKeys={detail.api_keys}
        actionsRestricted={actionsRestricted}
        pendingAction={pendingAction}
        onSetAPIKeyStatus={handleSetAPIKeyStatus}
      />

      <EditAccountSection
        identity={identity}
        isSelf={isSelf}
        actionsRestricted={actionsRestricted}
        isLocalMode={isLocalMode}
        canResetQuota={Boolean(currentUser?.is_omniadmin)}
        ownedAppCount={ownedAppCount}
        pendingAction={pendingAction}
        onSetPlatformRole={handleSetPlatformRole}
        onDeactivate={handleDeactivate}
        onActivate={handleActivate}
        onResetLink={handleResetLink}
        onResetQuota={handleResetQuota}
        onDelete={handleDelete}
      />

      {resetLinkState && (
        <OneTimeLinkModal
          isOpen
          onClose={() => setResetLinkState(null)}
          token={resetLinkState.token}
          expiresAt={resetLinkState.expiresAt}
          title="Password reset link"
        />
      )}
      {selectedMetricsApp && (
        <AdminAppMetricsModal
          appId={selectedMetricsApp.app_id}
          appName={appLabel(selectedMetricsApp.name, selectedMetricsApp.app_id)}
          onClose={() => setSelectedMetricsApp(null)}
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
