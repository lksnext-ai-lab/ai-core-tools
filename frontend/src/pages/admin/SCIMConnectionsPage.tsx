import { useEffect, useState } from 'react';
import type { SubmitEvent } from 'react';
import {
  apiService,
  type KeycloakReconciliationRequest,
  type KeycloakReconciliationResponse,
  type KeycloakTargetSetupResponse,
  type SCIMConnection,
  type SCIMConnectionCredential,
} from '../../services/api';

const fieldClassName =
  'w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100';
const labelClassName = 'mb-1 block text-sm font-medium text-gray-700 dark:text-gray-200';
const managementButtonFocusClassName =
  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 dark:focus-visible:ring-offset-gray-900';

const isKeycloakConnection = (item: SCIMConnection) =>
  item.provider_type.toLowerCase() === 'keycloak';

const isEntraConnection = (item: SCIMConnection) =>
  item.provider_type.toLowerCase() === 'entra';

const getDirectoryLabel = (item: SCIMConnection): string => {
  if (isKeycloakConnection(item)) return 'Keycloak realm';
  if (isEntraConnection(item)) return 'Entra tenant ID';
  return 'External directory ID';
};

const getReconciliationAnnouncement = (
  response: KeycloakReconciliationResponse,
): string => {
  const operation = response.dry_run ? 'Dry-run' : 'Real reconciliation';
  let outcome = 'completed';
  if (response.summary.blocked) {
    outcome = 'is blocked';
  } else if (response.dry_run) {
    outcome = 'completed; confirmation is available';
  }
  return `${operation} ${outcome}. ${response.summary.user_creates} users to create, `
    + `${response.summary.user_updates} to update, ${response.summary.user_removals} to remove; `
    + `${response.summary.group_upserts} groups to upsert and ${response.summary.group_removals} to remove.`;
};

type SCIMProvider = 'keycloak' | 'entra';

function SCIMConnectionsPage() {
  const [setupEnabled, setSetupEnabled] = useState<boolean | null>(null);
  const [connections, setConnections] = useState<SCIMConnection[]>([]);
  const [editingConnection, setEditingConnection] = useState<SCIMConnection | null>(null);
  const [editDisplayName, setEditDisplayName] = useState('');
  const [editDirectoryId, setEditDirectoryId] = useState('');
  const [editAdminBaseUrl, setEditAdminBaseUrl] = useState('http://localhost:8080');
  const [editAdminRealm, setEditAdminRealm] = useState('master');
  const [editAdminUsername, setEditAdminUsername] = useState('');
  const [editAdminPassword, setEditAdminPassword] = useState('');
  const [connection, setConnection] = useState<SCIMConnectionCredential | null>(null);
  const [result, setResult] = useState<KeycloakTargetSetupResponse | null>(null);
  const [providerType, setProviderType] = useState<SCIMProvider>('keycloak');
  const [directoryId, setDirectoryId] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [copiedField, setCopiedField] = useState<'url' | 'token' | null>(null);
  const [mattinBaseUrl, setMattinBaseUrl] = useState('http://host.docker.internal:8000/scim/v2');
  const [keycloakBaseUrl, setKeycloakBaseUrl] = useState('http://localhost:8080');
  const [adminRealm, setAdminRealm] = useState('master');
  const [adminUsername, setAdminUsername] = useState('');
  const [adminPassword, setAdminPassword] = useState('');
  const [targetName, setTargetName] = useState('');
  const [syncGroups, setSyncGroups] = useState(true);
  const [reconcileConnectionId, setReconcileConnectionId] = useState('');
  const [reconcileAdminBaseUrl, setReconcileAdminBaseUrl] = useState('http://localhost:8080');
  const [reconcileAdminRealm, setReconcileAdminRealm] = useState('master');
  const [reconcileAdminUsername, setReconcileAdminUsername] = useState('');
  const [reconcileAdminPassword, setReconcileAdminPassword] = useState('');
  const [reconcilePreview, setReconcilePreview] = useState<KeycloakReconciliationResponse | null>(null);
  const [reconcileResult, setReconcileResult] = useState<KeycloakReconciliationResponse | null>(null);
  const [confirmRealReconcile, setConfirmRealReconcile] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    Promise.all([
      apiService.getSCIMKeycloakLocalSetupStatus(),
      apiService.getSCIMConnections(),
    ])
      .then(([status, existingConnections]) => {
        if (!active) return;
        setSetupEnabled(status.enabled);
        setConnections(existingConnections);
        const firstActiveKeycloak = existingConnections.find(
          (item) => isKeycloakConnection(item) && item.is_active,
        );
        if (firstActiveKeycloak) setReconcileConnectionId(String(firstActiveKeycloak.id));
      })
      .catch((cause: unknown) => {
        if (active) {
          setError(cause instanceof Error ? cause.message : 'Could not load SCIM settings.');
        }
      });
    return () => {
      active = false;
    };
  }, []);

  const handleCreateConnection = async (event: SubmitEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);
    setResult(null);
    setCopiedField(null);
    setBusy(true);
    try {
      const created = await apiService.createSCIMConnection({
        provider_type: providerType,
        external_directory_id: directoryId.trim(),
        display_name: displayName.trim(),
        auth_mode: 'static_bearer',
      });
      setConnection(created);
      setConnections((current) => [created, ...current]);
      if (providerType === 'keycloak') {
        setTargetName(`mattin-${directoryId.trim()}`);
      }
    } catch (cause: unknown) {
      setError(cause instanceof Error ? cause.message : 'Could not create the SCIM connection.');
    } finally {
      setBusy(false);
    }
  };

  const handleCopy = async (value: string, field: 'url' | 'token') => {
    setError(null);
    try {
      await navigator.clipboard.writeText(value);
      setCopiedField(field);
    } catch {
      setError('Could not copy to the clipboard. Select and copy the value manually.');
    }
  };

  const handleConfigureTarget = async (event: SubmitEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!connection) return;
    setError(null);
    setResult(null);
    setBusy(true);
    try {
      const configured = await apiService.configureKeycloakSCIMTarget(connection.id, {
        mattin_scim_base_url: mattinBaseUrl.trim(),
        keycloak_admin_base_url: keycloakBaseUrl.trim(),
        keycloak_admin_realm: adminRealm.trim(),
        keycloak_admin_username: adminUsername.trim(),
        keycloak_admin_password: adminPassword,
        bearer_token: connection.bearer_token,
        keycloak_realm: directoryId.trim(),
        target_name: targetName.trim(),
        sync_groups: syncGroups,
      });
      setResult(configured);
    } catch (cause: unknown) {
      setError(cause instanceof Error ? cause.message : 'Could not configure the Keycloak target.');
    } finally {
      setAdminPassword('');
      setBusy(false);
    }
  };

  const handleStartEditing = (item: SCIMConnection) => {
    setEditingConnection(item);
    setEditDisplayName(item.display_name);
    setEditDirectoryId(item.external_directory_id ?? '');
    setEditAdminUsername('');
    setEditAdminPassword('');
    setError(null);
  };

  const handleCancelEditing = () => {
    setEditingConnection(null);
    setEditAdminUsername('');
    setEditAdminPassword('');
  };

  const handleUpdateConnection = async (event: SubmitEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!editingConnection) return;
    const updatedRealm = editDirectoryId.trim();
    const needsKeycloakCheck =
      isKeycloakConnection(editingConnection)
      && updatedRealm !== (editingConnection.external_directory_id ?? '');
    setError(null);
    setBusy(true);
    try {
      const update = {
        expected_external_directory_id: editingConnection.external_directory_id,
        display_name: editDisplayName.trim(),
        external_directory_id: updatedRealm,
        ...(needsKeycloakCheck
          ? {
              keycloak_admin_base_url: editAdminBaseUrl.trim(),
              keycloak_admin_realm: editAdminRealm.trim(),
              keycloak_admin_username: editAdminUsername.trim(),
              keycloak_admin_password: editAdminPassword,
            }
          : {}),
      };
      const updated = await apiService.updateSCIMConnection(editingConnection.id, update);
      setConnections((current) =>
        current.map((item) => (item.id === updated.id ? updated : item)),
      );
      setConnection((current) =>
        current?.id === updated.id ? { ...current, ...updated } : current,
      );
      setEditingConnection(null);
    } catch (cause: unknown) {
      setError(cause instanceof Error ? cause.message : 'Could not update the SCIM connection.');
    } finally {
      setEditAdminPassword('');
      setEditAdminUsername('');
      setBusy(false);
    }
  };

  const handleSetConnectionActive = async (item: SCIMConnection) => {
    if (
      item.is_active
      && !window.confirm(`Deactivate "${item.display_name}"? SCIM requests will stop being accepted.`)
    ) return;
    setError(null);
    setBusy(true);
    try {
      const updated = await apiService.setSCIMConnectionActive(item.id, !item.is_active);
      setConnections((current) =>
        current.map((connectionItem) =>
          connectionItem.id === updated.id ? updated : connectionItem,
        ),
      );
      if (!updated.is_active && reconcileConnectionId === String(updated.id)) {
        setReconcileConnectionId('');
        setReconcilePreview(null);
        setReconcileResult(null);
      }
    } catch (cause: unknown) {
      setError(cause instanceof Error ? cause.message : 'Could not change the SCIM connection status.');
    } finally {
      setBusy(false);
    }
  };

  const getReconciliationRequest = (
    password: string,
    confirmRealReconcileValue = false,
  ): KeycloakReconciliationRequest => ({
    keycloak_admin_base_url: reconcileAdminBaseUrl.trim(),
    keycloak_admin_realm: reconcileAdminRealm.trim(),
    keycloak_admin_username: reconcileAdminUsername.trim(),
    keycloak_admin_password: password,
    confirm_real_reconcile: confirmRealReconcileValue,
  });

  const handleReconciliationDryRun = async (event: SubmitEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!reconcileConnectionId) return;
    setError(null);
    setReconcilePreview(null);
    setReconcileResult(null);
    setConfirmRealReconcile(false);
    setBusy(true);
    try {
      const preview = await apiService.runSCIMKeycloakDryRun(
        Number(reconcileConnectionId),
        getReconciliationRequest(reconcileAdminPassword),
      );
      setReconcilePreview(preview);
    } catch (cause: unknown) {
      setError(cause instanceof Error ? cause.message : 'Could not preview the SCIM reconciliation.');
    } finally {
      setReconcileAdminPassword('');
      setBusy(false);
    }
  };

  const handleRealReconciliation = async () => {
    if (
      !reconcileConnectionId
      || !reconcilePreview?.preview_token
      || reconcilePreview.summary.blocked
    ) return;
    setError(null);
    setReconcileResult(null);
    setBusy(true);
    try {
      const completed = await apiService.runSCIMKeycloakReconciliation(
        Number(reconcileConnectionId),
        {
          ...getReconciliationRequest(reconcileAdminPassword, confirmRealReconcile),
          preview_token: reconcilePreview.preview_token,
        },
      );
      setReconcileResult(completed);
      setReconcilePreview(null);
      setConfirmRealReconcile(false);
    } catch (cause: unknown) {
      setError(cause instanceof Error ? cause.message : 'Could not run the SCIM reconciliation.');
    } finally {
      setReconcileAdminPassword('');
      setBusy(false);
    }
  };

  const renderReconciliationSummary = (response: KeycloakReconciliationResponse) => (
    <div className="mt-4 rounded-md border border-gray-300 p-4 text-sm dark:border-gray-700">
      <h3 className="font-semibold text-gray-900 dark:text-gray-100">
        {response.dry_run ? 'Dry-run results' : 'Reconciliation results'}
      </h3>
      <p className="mt-1">
        {response.summary.blocked ? 'Blocked by Keycloak.' : 'Not blocked.'}
        {' '}Local users: {response.summary.local_users}; remote users: {response.summary.remote_users}.
      </p>
      <dl className="mt-3 grid gap-2 sm:grid-cols-2">
        <div><dt className="inline font-medium">User creates: </dt><dd className="inline">{response.summary.user_creates}</dd></div>
        <div><dt className="inline font-medium">User updates: </dt><dd className="inline">{response.summary.user_updates}</dd></div>
        <div><dt className="inline font-medium">User removals: </dt><dd className="inline">{response.summary.user_removals}</dd></div>
        <div><dt className="inline font-medium">Group upserts: </dt><dd className="inline">{response.summary.group_upserts}</dd></div>
        <div><dt className="inline font-medium">Group removals: </dt><dd className="inline">{response.summary.group_removals}</dd></div>
        <div><dt className="inline font-medium">Unmanaged remote users: </dt><dd className="inline">{response.summary.unmanaged_remote_users}</dd></div>
      </dl>
      {response.summary.message && <p className="mt-2">{response.summary.message}</p>}
    </div>
  );

  const renderCreatedConnection = () => {
    if (!connection) return null;

    return (
      <div className="mt-5 rounded-md border border-green-300 bg-green-50 p-4 dark:border-green-800 dark:bg-green-950/20">
        <h3 className="font-medium text-green-900 dark:text-green-200">
          Connection created: {connection.display_name}
        </h3>
        <label htmlFor="scim-bearer-token" className={`${labelClassName} mt-3`}>
          Mattin SCIM bearer token (shown once)
        </label>
        <input
          id="scim-bearer-token"
          className={fieldClassName}
          type="password"
          readOnly
          value={connection.bearer_token}
          autoComplete="new-password"
        />
        {providerType === 'keycloak' ? (
          <p className="mt-2 text-xs text-green-900 dark:text-green-200">
            Keep this page open until Keycloak is configured. The token exists only in this page's memory.
          </p>
        ) : (
          <div className="mt-3 space-y-4">
            <div>
              <label htmlFor="entra-scim-url" className={labelClassName}>Mattin SCIM base URL</label>
              <input
                id="entra-scim-url"
                className={fieldClassName}
                readOnly
                value={apiService.getSCIMBaseUrl(connection.connection_key)}
              />
              <button
                type="button"
                onClick={() => void handleCopy(
                  apiService.getSCIMBaseUrl(connection.connection_key),
                  'url',
                )}
                className={`mt-2 rounded-md border border-gray-300 px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50 dark:border-gray-600 dark:text-gray-200 dark:hover:bg-gray-800 ${managementButtonFocusClassName}`}
              >
                {copiedField === 'url' ? 'URL copied' : 'Copy URL'}
              </button>
            </div>
            <button
              type="button"
              onClick={() => void handleCopy(connection.bearer_token, 'token')}
              className={`rounded-md border border-gray-300 px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50 dark:border-gray-600 dark:text-gray-200 dark:hover:bg-gray-800 ${managementButtonFocusClassName}`}
            >
              {copiedField === 'token' ? 'Token copied' : 'Copy token'}
            </button>
            <div className="space-y-2 text-sm text-green-950 dark:text-green-100">
              <h3 className="font-semibold">Configure provisioning in Microsoft Entra</h3>
              <ol className="list-decimal space-y-1 pl-5">
                <li>In Entra admin center, create an Enterprise application for a non-gallery app.</li>
                <li>Open <strong>Provisioning</strong>, create a configuration, and enter the SCIM URL and bearer token above.</li>
                <li>Run <strong>Test Connection</strong>, then save the configuration.</li>
                <li>Set the scope to assigned users and groups, and assign a small pilot group first.</li>
                <li>Map <code>userName</code> to <code>userPrincipalName</code> and use it as the user matching attribute. Map <code>externalId</code> to the stable user object ID.</li>
                <li>If provisioning groups, map <code>displayName</code> and <code>externalId</code> (group object ID), then test membership changes.</li>
              </ol>
              <p>
                Keep the default <code>active</code> mapping and verify that disabling and re-enabling a pilot user
                changes the Mattin account status as expected. Configure only mappings supported by Mattin.
              </p>
              <p>
                The URL and token are held only in this page&apos;s memory. Copy the token before leaving; if it is lost,
                rotate the connection token and update Entra.
              </p>
            </div>
          </div>
        )}
      </div>
    );
  };

  const renderKeycloakResult = () => {
    if (!result) return null;

    return (
      <>
        {result.test_ok && (
          <output className="sr-only" aria-live="polite">
            Keycloak target created and tested. Target: {result.target_name}; HTTP {result.test_status ?? 'unknown'}.
            PATCH: {result.patch_supported ? 'supported' : 'not reported'}; filters: {result.filter_supported ? 'supported' : 'not reported'}.
          </output>
        )}
        <section
          role={result.test_ok ? undefined : 'alert'}
          className={`rounded-lg border p-4 ${
            result.test_ok
              ? 'border-green-300 bg-green-50 text-green-900 dark:border-green-800 dark:bg-green-950/20 dark:text-green-200'
              : 'border-red-300 bg-red-50 text-red-900 dark:border-red-800 dark:bg-red-950/30 dark:text-red-200'
          }`}
        >
          <h2 className="font-semibold">
            {result.test_ok ? 'Keycloak target created and tested' : 'Target created, but its connection test failed'}
          </h2>
          <p className="mt-1 text-sm">
            Target: {result.target_name} ({result.target_id}); HTTP {result.test_status ?? 'unknown'}.
          </p>
          {result.test_ok && (
            <p className="mt-1 text-sm">
              PATCH: {result.patch_supported ? 'supported' : 'not reported'}; filters: {result.filter_supported ? 'supported' : 'not reported'}.
            </p>
          )}
        </section>
      </>
    );
  };

  const renderReconciliationResults = () => (
    <>
      <output className="sr-only" aria-live="polite" aria-atomic="true">
        {reconciliationStatus ? getReconciliationAnnouncement(reconciliationStatus) : ''}
      </output>
      {reconcilePreview && renderReconciliationSummary(reconcilePreview)}
      {reconcilePreview && !reconcilePreview.summary.blocked && (
        <div className="mt-4 space-y-3 rounded-md border border-amber-300 bg-amber-50 p-4 text-sm text-amber-950 dark:border-amber-700 dark:bg-amber-950/30 dark:text-amber-100">
          <h3 className="font-semibold">Confirm real reconciliation</h3>
          <p>Review the preview carefully. This will apply the changes shown above to Mattin.</p>
          <label className="flex items-start gap-2">
            <input
              type="checkbox"
              checked={confirmRealReconcile}
              onChange={(event) => setConfirmRealReconcile(event.target.checked)}
              disabled={busy}
            />
            <span>I understand and want to apply these changes to Mattin.</span>
          </label>
          <div>
            <label htmlFor="confirm-reconcile-password" className={labelClassName}>Re-enter Keycloak admin password</label>
            <input
              id="confirm-reconcile-password"
              className={fieldClassName}
              type="password"
              value={reconcileAdminPassword}
              onChange={(event) => setReconcileAdminPassword(event.target.value)}
              autoComplete="current-password"
              required
              disabled={busy}
            />
          </div>
          <button
            type="button"
            onClick={handleRealReconciliation}
            disabled={
              busy
              || !reconcilePreview.preview_token
              || !confirmRealReconcile
              || !reconcileAdminPassword
            }
            className="rounded-md bg-red-700 px-4 py-2 text-sm font-medium text-white hover:bg-red-800 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {busy ? 'Running reconciliation…' : 'Confirm and run real reconciliation'}
          </button>
        </div>
      )}
      {reconcileResult && renderReconciliationSummary(reconcileResult)}
    </>
  );

  const reconciliationStatus = reconcilePreview ?? reconcileResult;

  return (
    <div className="mx-auto max-w-5xl space-y-6 p-6">
      <header>
        <h1 className="text-2xl font-semibold text-gray-900 dark:text-gray-100">
          SCIM connections
        </h1>
        <p className="mt-1 text-sm text-gray-600 dark:text-gray-300">
          Create a provider-specific Mattin SCIM connection. Keycloak has a local setup wizard; Entra provides guided configuration.
        </p>
      </header>

      {providerType === 'keycloak' && (
      <section
        aria-labelledby="local-test-warning"
        className="rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm text-amber-950 dark:border-amber-700 dark:bg-amber-950/30 dark:text-amber-100"
      >
        <h2 id="local-test-warning" className="font-semibold">Local testing only</h2>
        <p className="mt-1">
          This assistant sends temporary Keycloak admin-cli credentials to the Mattin backend and configures
          the target with the SCIM bearer token. Mattin does not store the Keycloak credentials or the raw
          bearer token. Do not use this flow for production.
        </p>
      </section>
      )}

      {providerType === 'keycloak' && setupEnabled === false && (
        <output className="block rounded-md border border-gray-300 p-4 text-sm dark:border-gray-700">
          Auto-setup is disabled. The operator must set{' '}
          <code className="font-mono">SCIM_KEYCLOAK_LOCAL_AUTOCONNECT_ENABLED=true</code> and restart the backend.
        </output>
      )}

      {error && (
        <div role="alert" className="rounded-md border border-red-300 bg-red-50 p-3 text-sm text-red-800 dark:border-red-800 dark:bg-red-950/30 dark:text-red-200">
          {error}
        </div>
      )}

      <section className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm dark:border-gray-700 dark:bg-gray-900">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">1. Create a Mattin connection</h2>
        <p className="mt-1 text-sm text-gray-600 dark:text-gray-300">
          Mattin generates the connection URL and bearer token. The token is shown only once.
        </p>
        <form className="mt-4 grid gap-4 sm:grid-cols-2" onSubmit={handleCreateConnection}>
          <div>
            <label htmlFor="scim-provider" className={labelClassName}>Provider</label>
            <select
              id="scim-provider"
              className={fieldClassName}
              value={providerType}
              onChange={(event) => {
                const nextProvider = event.target.value;
                if (nextProvider === 'keycloak' || nextProvider === 'entra') {
                  setProviderType(nextProvider);
                }
              }}
              disabled={busy || Boolean(connection)}
            >
              <option value="keycloak">Keycloak</option>
              <option value="entra">Microsoft Entra ID</option>
            </select>
          </div>
          <div>
            <label htmlFor="scim-directory-id" className={labelClassName}>
              {providerType === 'keycloak' ? 'Keycloak realm' : 'Entra tenant ID'}
            </label>
            <input
              id="scim-directory-id"
              className={fieldClassName}
              value={directoryId}
              onChange={(event) => setDirectoryId(event.target.value)}
              required
              maxLength={255}
              disabled={busy || (providerType === 'keycloak' && setupEnabled !== true) || Boolean(connection)}
            />
          </div>
          <div>
            <label htmlFor="scim-display-name" className={labelClassName}>Connection name</label>
            <input
              id="scim-display-name"
              className={fieldClassName}
              value={displayName}
              onChange={(event) => setDisplayName(event.target.value)}
              required
              maxLength={255}
              placeholder={providerType === 'keycloak' ? 'Keycloak test realm' : 'Entra tenant'}
              disabled={busy || (providerType === 'keycloak' && setupEnabled !== true) || Boolean(connection)}
            />
          </div>
          <div className="sm:col-span-2">
            <button
              type="submit"
              disabled={busy || (providerType === 'keycloak' && setupEnabled !== true) || Boolean(connection)}
              className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              Create SCIM connection
            </button>
          </div>
        </form>

        {renderCreatedConnection()}
      </section>

      {connection && providerType === 'keycloak' && (
        <section className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm dark:border-gray-700 dark:bg-gray-900">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">2. Configure and test Keycloak</h2>
          <form className="mt-4 grid gap-4 sm:grid-cols-2" onSubmit={handleConfigureTarget}>
            <div>
              <label htmlFor="mattin-base-url" className={labelClassName}>Mattin SCIM base URL, reachable from Keycloak</label>
              <input
                id="mattin-base-url"
                className={fieldClassName}
                type="url"
                value={mattinBaseUrl}
                onChange={(event) => setMattinBaseUrl(event.target.value)}
                required
              />
            </div>
            <div>
              <label htmlFor="keycloak-base-url" className={labelClassName}>Keycloak Admin URL, reachable from Mattin</label>
              <input
                id="keycloak-base-url"
                className={fieldClassName}
                type="url"
                value={keycloakBaseUrl}
                onChange={(event) => setKeycloakBaseUrl(event.target.value)}
                required
              />
            </div>
            <div>
              <label htmlFor="keycloak-admin-realm" className={labelClassName}>Admin realm</label>
              <input
                id="keycloak-admin-realm"
                className={fieldClassName}
                value={adminRealm}
                onChange={(event) => setAdminRealm(event.target.value)}
                required
              />
            </div>
            <div>
              <label htmlFor="keycloak-admin-username" className={labelClassName}>Keycloak admin username</label>
              <input
                id="keycloak-admin-username"
                className={fieldClassName}
                value={adminUsername}
                onChange={(event) => setAdminUsername(event.target.value)}
                autoComplete="username"
                required
              />
            </div>
            <div>
              <label htmlFor="keycloak-admin-password" className={labelClassName}>Keycloak admin password</label>
              <input
                id="keycloak-admin-password"
                className={fieldClassName}
                type="password"
                value={adminPassword}
                onChange={(event) => setAdminPassword(event.target.value)}
                autoComplete="current-password"
                required
              />
            </div>
            <div>
              <label htmlFor="keycloak-target-name" className={labelClassName}>Keycloak target name</label>
              <input
                id="keycloak-target-name"
                className={fieldClassName}
                value={targetName}
                onChange={(event) => setTargetName(event.target.value)}
                required
                maxLength={255}
              />
            </div>
            <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-200 sm:col-span-2">
              <input
                type="checkbox"
                checked={syncGroups}
                onChange={(event) => setSyncGroups(event.target.checked)}
              />
              <span>Synchronize groups</span>
            </label>
            <div className="sm:col-span-2">
              <button
                type="submit"
                disabled={busy}
                className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {busy ? 'Configuring…' : 'Create target and test connection'}
              </button>
            </div>
          </form>
        </section>
      )}

      {renderKeycloakResult()}

      <section className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm dark:border-gray-700 dark:bg-gray-900">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">3. Preview and run reconciliation</h2>
        <p className="mt-1 text-sm text-gray-600 dark:text-gray-300">
          Reconciliation can create, update, or deactivate users in Mattin. Review the dry-run before confirming a real run.
        </p>
        <form className="mt-4 grid gap-4 sm:grid-cols-2" onSubmit={handleReconciliationDryRun}>
          <div className="sm:col-span-2">
            <label htmlFor="scim-reconcile-connection" className={labelClassName}>SCIM connection / Keycloak realm</label>
            <select
              id="scim-reconcile-connection"
              className={fieldClassName}
              value={reconcileConnectionId}
              onChange={(event) => {
                setReconcileConnectionId(event.target.value);
                setReconcilePreview(null);
                setReconcileResult(null);
                setConfirmRealReconcile(false);
              }}
              required
              disabled={busy}
            >
              <option value="">Select an active Keycloak connection</option>
              {connections
                .filter((item) => isKeycloakConnection(item) && item.is_active)
                .map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.display_name} ({item.external_directory_id})
                  </option>
                ))}
            </select>
          </div>
          <div>
            <label htmlFor="reconcile-keycloak-url" className={labelClassName}>Keycloak Admin URL</label>
            <input
              id="reconcile-keycloak-url"
              className={fieldClassName}
              type="url"
              value={reconcileAdminBaseUrl}
              onChange={(event) => setReconcileAdminBaseUrl(event.target.value)}
              required
              disabled={busy}
            />
          </div>
          <div>
            <label htmlFor="reconcile-admin-realm" className={labelClassName}>Admin realm</label>
            <input
              id="reconcile-admin-realm"
              className={fieldClassName}
              value={reconcileAdminRealm}
              onChange={(event) => setReconcileAdminRealm(event.target.value)}
              required
              disabled={busy}
            />
          </div>
          <div>
            <label htmlFor="reconcile-admin-username" className={labelClassName}>Keycloak admin username</label>
            <input
              id="reconcile-admin-username"
              className={fieldClassName}
              value={reconcileAdminUsername}
              onChange={(event) => setReconcileAdminUsername(event.target.value)}
              autoComplete="username"
              required
              disabled={busy}
            />
          </div>
          <div>
            <label htmlFor="reconcile-admin-password" className={labelClassName}>Keycloak admin password</label>
            <input
              id="reconcile-admin-password"
              className={fieldClassName}
              type="password"
              value={reconcileAdminPassword}
              onChange={(event) => setReconcileAdminPassword(event.target.value)}
              autoComplete="current-password"
              required
              disabled={busy}
            />
          </div>
          <div className="sm:col-span-2">
            <button
              type="submit"
              disabled={busy || !reconcileConnectionId || setupEnabled !== true}
              className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {busy ? 'Running dry-run…' : 'Run dry-run'}
            </button>
          </div>
        </form>

        {renderReconciliationResults()}
      </section>

      <section className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm dark:border-gray-700 dark:bg-gray-900">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">Existing SCIM connections</h2>
        {connections.length === 0 ? (
          <p className="mt-2 text-sm text-gray-600 dark:text-gray-300">No connections found.</p>
        ) : (
          <ul className="mt-3 divide-y divide-gray-200 dark:divide-gray-700">
            {connections.map((item) => (
              <li key={item.id} className="py-3 text-sm">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <span className="font-medium text-gray-900 dark:text-gray-100">{item.display_name}</span>
                    <span className="ml-2 text-gray-600 dark:text-gray-300">
                      {getDirectoryLabel(item)}: {item.external_directory_id ?? '—'} · {item.is_active ? 'Active' : 'Inactive'}
                    </span>
                  </div>
                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={() => handleStartEditing(item)}
                      disabled={busy}
                      aria-label={`Edit ${item.display_name}`}
                      className={`rounded-md border border-gray-300 px-3 py-1.5 font-medium text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-gray-600 dark:text-gray-200 dark:hover:bg-gray-800 ${managementButtonFocusClassName}`}
                    >
                      Edit
                    </button>
                    <button
                      type="button"
                      onClick={() => void handleSetConnectionActive(item)}
                      disabled={busy}
                      aria-label={`${item.is_active ? 'Deactivate' : 'Activate'} ${item.display_name}`}
                      className={`rounded-md border border-gray-300 px-3 py-1.5 font-medium text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-gray-600 dark:text-gray-200 dark:hover:bg-gray-800 ${managementButtonFocusClassName}`}
                    >
                      {item.is_active ? 'Deactivate' : 'Activate'}
                    </button>
                  </div>
                </div>
                {editingConnection?.id === item.id && (
                  <form
                    className="mt-4 grid gap-4 rounded-md border border-gray-200 p-4 dark:border-gray-700 sm:grid-cols-2"
                    onSubmit={handleUpdateConnection}
                  >
                    <div>
                      <label htmlFor="edit-scim-name" className={labelClassName}>Connection name</label>
                      <input
                        id="edit-scim-name"
                        className={fieldClassName}
                        value={editDisplayName}
                        onChange={(event) => setEditDisplayName(event.target.value)}
                        maxLength={255}
                        required
                        disabled={busy}
                      />
                    </div>
                    <div>
                      <label htmlFor="edit-scim-directory" className={labelClassName}>
                      {getDirectoryLabel(item)}
                      </label>
                      <input
                        id="edit-scim-directory"
                        className={fieldClassName}
                        value={editDirectoryId}
                        onChange={(event) => setEditDirectoryId(event.target.value)}
                        maxLength={255}
                        required
                        disabled={busy}
                      />
                    </div>
                    {isKeycloakConnection(item)
                      && editDirectoryId.trim() !== (item.external_directory_id ?? '') && (
                      <div className="space-y-3 rounded-md border border-amber-300 bg-amber-50 p-3 text-amber-950 dark:border-amber-700 dark:bg-amber-950/30 dark:text-amber-100 sm:col-span-2">
                        <p>
                          Mattin will check the current and new realms. If a target for this connection exists in either realm,
                          the realm change will be rejected. Target configuration is not moved.
                        </p>
                        {setupEnabled === false && (
                          <output className="block">
                            Realm changes require <code>SCIM_KEYCLOAK_LOCAL_AUTOCONNECT_ENABLED=true</code>.
                          </output>
                        )}
                        <div className="grid gap-3 sm:grid-cols-2">
                          <div>
                            <label htmlFor="edit-keycloak-admin-url" className={labelClassName}>Keycloak Admin URL</label>
                            <input
                              id="edit-keycloak-admin-url"
                              className={fieldClassName}
                              type="url"
                              value={editAdminBaseUrl}
                              onChange={(event) => setEditAdminBaseUrl(event.target.value)}
                              required
                              disabled={busy}
                            />
                          </div>
                          <div>
                            <label htmlFor="edit-keycloak-admin-realm" className={labelClassName}>Admin realm</label>
                            <input
                              id="edit-keycloak-admin-realm"
                              className={fieldClassName}
                              value={editAdminRealm}
                              onChange={(event) => setEditAdminRealm(event.target.value)}
                              required
                              disabled={busy}
                            />
                          </div>
                          <div>
                            <label htmlFor="edit-keycloak-admin-username" className={labelClassName}>Keycloak admin username</label>
                            <input
                              id="edit-keycloak-admin-username"
                              className={fieldClassName}
                              value={editAdminUsername}
                              onChange={(event) => setEditAdminUsername(event.target.value)}
                              autoComplete="username"
                              required
                              disabled={busy}
                            />
                          </div>
                          <div>
                            <label htmlFor="edit-keycloak-admin-password" className={labelClassName}>Keycloak admin password</label>
                            <input
                              id="edit-keycloak-admin-password"
                              className={fieldClassName}
                              type="password"
                              value={editAdminPassword}
                              onChange={(event) => setEditAdminPassword(event.target.value)}
                              autoComplete="current-password"
                              required
                              disabled={busy}
                            />
                          </div>
                        </div>
                      </div>
                    )}
                    <div className="flex gap-2 sm:col-span-2">
                      <button
                        type="submit"
                        disabled={
                          busy
                          || (isKeycloakConnection(item)
                            && editDirectoryId.trim() !== (item.external_directory_id ?? '')
                            && setupEnabled !== true)
                        }
                        className={`rounded-md bg-blue-600 px-4 py-2 font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50 ${managementButtonFocusClassName}`}
                      >
                        {busy ? 'Saving…' : 'Save changes'}
                      </button>
                      <button
                        type="button"
                        onClick={handleCancelEditing}
                        disabled={busy}
                        className={`rounded-md border border-gray-300 px-4 py-2 font-medium text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-gray-600 dark:text-gray-200 dark:hover:bg-gray-800 ${managementButtonFocusClassName}`}
                      >
                        Cancel
                      </button>
                    </div>
                  </form>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

export default SCIMConnectionsPage;
