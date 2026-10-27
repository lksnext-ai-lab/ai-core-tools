import { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { RefreshCw, SquareArrowOutUpRight, Trash2 } from 'lucide-react';
import Alert from '../components/ui/Alert';
import { TagInput } from '../components/ui/TagInput';
import { useAppRole } from '../hooks/useAppRole';
import { AppRole } from '../types/roles';
import { useConfirm } from '../contexts/ConfirmContext';
import { sharepointApi } from '../services/sharepoint';
import type { SharePointSourceDetail, SharePointSyncStatus } from '../types/sharepoint';
import { MESSAGES, errorMessage } from '../constants/messages';
import { useApiMutation } from '../hooks/useApiMutation';
import { LoadingState } from '../components/ui/LoadingState';
import { ButtonApp } from '../components/ui/ButtonApp';
import { FormField, FormTextArea } from '../components/ui/FormField';
import { Spinner } from '../components/ui/Spinner';
import { Badge, type BadgeVariant } from '../components/ui/Badge';
import Title from '../components/ui/Title';
import CardApp from '../components/ui/CardApp';

const STATUS_BADGE: Record<SharePointSyncStatus, { label: string; variant: BadgeVariant }> = {
  IDLE: { label: 'Idle', variant: 'default' },
  RUNNING: { label: 'Running', variant: 'info' },
  SUCCESS: { label: 'Success', variant: 'success' },
  PARTIAL: { label: 'Partial', variant: 'warning' },
  ERROR: { label: 'Error', variant: 'error' },
};

function relativeTime(iso: string | null): string {
  if (!iso) return 'Never';
  const diff = Date.now() - new Date(iso).getTime();
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return 'Just now';
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

function SharePointSourceDetailPage() {
  const { appId, sourceId } = useParams<{ appId: string; sourceId: string }>();
  const navigate = useNavigate();
  const { hasMinRole } = useAppRole(appId);
  const canEdit = hasMinRole(AppRole.EDITOR);
  const canDelete = hasMinRole(AppRole.ADMINISTRATOR);
  const confirm = useConfirm();
  const mutate = useApiMutation();

  const [source, setSource] = useState<SharePointSourceDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // General section
  const [generalName, setGeneralName] = useState('');
  const [generalDesc, setGeneralDesc] = useState('');
  const [generalSaving, setGeneralSaving] = useState(false);
  const [generalError, setGeneralError] = useState<string | null>(null);

  // Credentials section
  const [credTenantId, setCredTenantId] = useState('');
  const [credClientId, setCredClientId] = useState('');
  const [credSecret, setCredSecret] = useState('');
  const [credSaving, setCredSaving] = useState(false);
  const [credError, setCredError] = useState<string | null>(null);

  // Filters section
  const [fileExtensions, setFileExtensions] = useState<string[]>([]);
  const [filtersSaving, setFiltersSaving] = useState(false);
  const [filtersError, setFiltersError] = useState<string | null>(null);

  // Sync
  const [syncing, setSyncing] = useState(false);
  const [syncError, setSyncError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    void loadSource();
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [appId, sourceId]);

  // Poll while RUNNING
  useEffect(() => {
    if (!source) return;
    if (source.last_sync_status === 'RUNNING') {
      if (!pollRef.current) {
        pollRef.current = setInterval(() => {
          void loadSource(true);
        }, 5000);
      }
    } else {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    }
  }, [source?.last_sync_status]);

  async function loadSource(silent = false) {
    if (!appId || !sourceId) return;
    try {
      if (!silent) setLoading(true);
      const data = await sharepointApi.getSource(Number(appId), Number(sourceId));
      setSource(data);
      if (!silent) {
        setGeneralName(data.name);
        setGeneralDesc(data.description ?? '');
        setFileExtensions(data.file_extension_filters ?? []);
      }
    } catch (err: any) {
      if (!silent) setError(err?.message ?? 'Failed to load source');
    } finally {
      if (!silent) setLoading(false);
    }
  }

  async function handleSaveGeneral() {
    if (!appId || !sourceId) return;
    setGeneralSaving(true);
    setGeneralError(null);
    try {
      const updated = await sharepointApi.updateSource(Number(appId), Number(sourceId), {
        name: generalName,
        description: generalDesc || undefined,
      });
      setSource((prev) => prev ? { ...prev, ...updated } : prev);
    } catch (err: any) {
      setGeneralError(err?.message ?? 'Failed to save changes.');
    } finally {
      setGeneralSaving(false);
    }
  }

  async function handleSaveCredentials() {
    if (!appId || !sourceId) return;
    setCredSaving(true);
    setCredError(null);
    try {
      const patch: Record<string, string> = {};
      if (credTenantId) patch.tenant_id = credTenantId;
      if (credClientId) patch.client_id = credClientId;
      if (credSecret) patch.client_secret = credSecret;
      if (Object.keys(patch).length === 0) return;
      const updated = await sharepointApi.updateSource(Number(appId), Number(sourceId), patch);
      setSource((prev) => prev ? { ...prev, ...updated } : prev);
      setCredTenantId('');
      setCredClientId('');
      setCredSecret('');
    } catch (err: any) {
      setCredError(err?.message ?? 'Failed to update credentials. Check values and try again.');
    } finally {
      setCredSaving(false);
    }
  }

  async function handleSaveFilters() {
    if (!appId || !sourceId) return;
    setFiltersSaving(true);
    setFiltersError(null);
    try {
      const updated = await sharepointApi.updateSource(Number(appId), Number(sourceId), {
        file_extension_filters: fileExtensions,
      });
      setSource((prev) => prev ? { ...prev, ...updated } : prev);
    } catch (err: any) {
      setFiltersError(err?.message ?? 'Failed to save filters.');
    } finally {
      setFiltersSaving(false);
    }
  }

  async function handleSync() {
    if (!appId || !sourceId) return;
    setSyncing(true);
    setSyncError(null);
    try {
      await sharepointApi.triggerSync(Number(appId), Number(sourceId));
      setSource((prev) =>
        prev ? { ...prev, last_sync_status: 'RUNNING' as const } : prev,
      );
    } catch (err: any) {
      const msg = err?.message ?? '';
      if (msg.includes('409') || msg.toLowerCase().includes('already')) {
        setSource((prev) =>
          prev ? { ...prev, last_sync_status: 'RUNNING' as const } : prev,
        );
      } else {
        setSyncError(msg || 'Failed to trigger sync.');
      }
    } finally {
      setSyncing(false);
    }
  }

  async function handleDelete() {
    if (!appId || !sourceId) return;
    const ok = await confirm({
      title: MESSAGES.CONFIRM_DELETE_TITLE('SharePoint source'),
      message:
        'This will delete all indexed content from the associated silo. This action cannot be undone.',
      variant: 'danger',
      confirmLabel: 'Delete',
    });
    if (!ok) return;

    const result = await mutate(
      () => sharepointApi.deleteSource(Number(appId), Number(sourceId)),
      {
        loading: MESSAGES.DELETING('SharePoint source'),
        success: MESSAGES.DELETED('SharePoint source'),
        error: (err) => errorMessage(err, MESSAGES.DELETE_FAILED('SharePoint source')),
      },
    );
    if (result === undefined) return;
    navigate(`/apps/${appId}/sharepoint`);
  }

  if (loading) {
    return (
      <LoadingState variant="page" message="Loading..." />
    );
  }

  if (error || !source) {
    return (
      <Alert
        type="error"
        title="Failed to load source"
        message={error ?? 'Source not found'}
        onDismiss={() => navigate(`/apps/${appId}/sharepoint`)}
      />
    );
  }

  const isRunning = source.last_sync_status === 'RUNNING' || syncing;
  const statusBadge = STATUS_BADGE[source.last_sync_status] ?? STATUS_BADGE.IDLE;

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <Title variant="titSecundario" titulo={source.name} subtitulo={source.description?source.description:''} />
        {canEdit && (
          <ButtonApp
            label={isRunning ? 'Syncing...' : 'Sync now'}
            onClick={() => { void handleSync(); }}
            loading={isRunning}
            icon={<RefreshCw className="w-4 h-4" />}
          />
        )}
      </div>

      {syncError && (
        <Alert type="error" title="Sync Error" message={syncError} onDismiss={() => setSyncError(null)} />
      )}

      {/* Sync status panel */}
      <CardApp className="p-5">
        <h3 className="text-lg font-semibold text-fg dark:text-fg-dark mb-3">Sync Status</h3>
        <div className="flex flex-wrap justify-between gap-6">
          <div>
            <span className="text-xs text-fg-secondary dark:text-fg-secondary-dark">Status</span>
            <div className="mt-1">
              <Badge
                label={statusBadge.label}
                variant={statusBadge.variant}
                icon={source.last_sync_status === 'RUNNING' ? <Spinner size="xs" tone="current" /> : undefined}
              />
            </div>
          </div>
          <div>
            <span className="text-xs text-fg-secondary dark:text-fg-secondary-dark">Last synced</span>
            <p
              className="text-sm text-fg dark:text-fg-dark mt-1"
              title={
                source.last_synced_at
                  ? new Date(source.last_synced_at).toLocaleString()
                  : 'Never'
              }
            >
              {relativeTime(source.last_synced_at)}
            </p>
          </div>
          <div>
            <span className="text-xs text-fg-secondary dark:text-fg-secondary-dark">Files indexed</span>
            <p className="text-sm text-fg dark:text-fg-dark mt-1">{source.file_count}</p>
          </div>
        </div>
        {source.last_sync_error && (
          <Alert
            type="error"
            title="Sync error"
            message={source.last_sync_error}
            className="mt-3"
          />
        )}
      </CardApp>

      {/* General section */}
      {canEdit && (
        <CardApp className="p-5">
          <h3 className="text-lg font-semibold text-fg dark:text-fg-dark mb-3">General</h3>
          {generalError && (
            <Alert
              type="error"
              title="Save failed"
              message={generalError}
              onDismiss={() => setGeneralError(null)}
              className="mb-3"
            />
          )}
          <div className="space-y-3">
            <FormField
              label="Name"
              id="general-name"
              value={generalName}
              onChange={(e) => setGeneralName(e.target.value)}
            />
            <FormTextArea
              label="Description"
              id="general-description"
              value={generalDesc}
              onChange={(e) => setGeneralDesc(e.target.value)}
              rows={2}
            />
            <div className="flex justify-end">
              <ButtonApp
                label={generalSaving ? 'Saving...' : 'Save'}
                onClick={() => { void handleSaveGeneral(); }}
                disabled={generalSaving}
                variant="primary"
                size="medium"
              />
            </div>
          </div>
        </CardApp>
      )}

      {/* SharePoint connection section */}
      <CardApp className="p-5">
        <h3 className="text-lg font-semibold text-fg dark:text-fg-dark mb-3">SharePoint Connection</h3>

        {/* Read-only site/drive info */}
        <div className="grid grid-cols-2 gap-4 mb-4">
          <div>
            <span className="text-xs text-fg-secondary dark:text-fg-secondary-dark">Site</span>
            <p className="text-sm text-fg dark:text-fg-dark mt-0.5">{source.site_name ?? source.site_id}</p>
            {source.site_url && (
              <a
                href={source.site_url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs text-bronze  dark:text-bronze-dark inline-block">
                {source.site_url}{''}<SquareArrowOutUpRight className="w-3 h-3 inline-block ml-1" aria-hidden="true" />

              </a>
            )}
          </div>
          <div>
            <span className="text-xs text-fg dark:text-fg-dark">Drive</span>
            <p className="text-sm text-fg dark:text-fg-dark mt-0.5">{source.drive_name ?? source.drive_id}</p>
          </div>
        </div>

        {/* Editable credentials */}
        {canEdit && (
          <>
            {credError && (
              <Alert
                type="error"
                title="Credential update failed"
                message={credError}
                onDismiss={() => setCredError(null)}
                className="mb-3"
              />
            )}
            <div className="space-y-3">
              <FormField
                label="Tenant ID"
                id="tenant-id"
                value={credTenantId}
                onChange={(e) => setCredTenantId(e.target.value)}
                placeholder={`Current: ${source.tenant_id}`}
                helpText="Leave credential fields blank to keep the current values. All three fields must be provided together if you want to update credentials."
              />
              <FormField
                label="Client ID"
                id="client-id"
                value={credClientId}
                onChange={(e) => setCredClientId(e.target.value)}
                placeholder={`Current: ${source.client_id}`}
              />
              <FormField
                label="Client Secret"
                id="client-secret"
                type="password"
                value={credSecret}
                onChange={(e) => setCredSecret(e.target.value)}
                placeholder="Leave blank to keep current"
                helpText={(credTenantId || credClientId || credSecret)
                  ? 'Credentials will be validated against Microsoft Graph on save.'
                  : undefined}
              />
              <div className="flex justify-end">
                <ButtonApp
                  label={credSaving ? 'Validating...' : 'Update Credentials'}
                  onClick={() => { void handleSaveCredentials(); }}
                  disabled={credSaving || (!credTenantId && !credClientId && !credSecret)}
                  variant="primary"
                  size="medium"
                />
              </div>
            </div>
          </>
        )}
      </CardApp>

      {/* Indexing config section */}
      {canEdit && (
        <CardApp className="p-5">
          <h3 className="text-lg font-semibold text-fg dark:text-fg-dark mb-3">Indexing Config</h3>
          {filtersError && (
            <Alert
              type="error"
              title="Save failed"
              message={filtersError}
              onDismiss={() => setFiltersError(null)}
              className="mb-3"
            />
          )}
          <div className="space-y-3">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                File Extension Filters
              </label>
              <TagInput
                tags={fileExtensions}
                onChange={setFileExtensions}
                maxTags={20}
                placeholder="e.g. pdf, docx — press Enter"
              />
              <p className="text-xs text-gray-500 mt-1">Empty = index all supported types.</p>
            </div>
            <div className="flex justify-end">
              <ButtonApp
                label={filtersSaving ? 'Saving...' : 'Save Filters'}
                onClick={() => { void handleSaveFilters(); }}
                disabled={filtersSaving}
                variant="primary"
                size="medium"
              />
            </div>
          </div>
        </CardApp>
      )}

      {/* Danger zone */}
      {canDelete && (
        <CardApp className="border-error p-5">
          <h3 className="text-lg font-semibold text-error mb-3">Danger Zone</h3>
          <p className="text-sm text-gray-600 mb-3">
            Deleting this source will permanently remove all indexed documents from the associated
            silo. This action cannot be undone.
          </p>
          <ButtonApp
            label="Delete Source"
            onClick={() => { void handleDelete(); }}
            variant="dangerSolid"
            size="medium"
            icon={<Trash2 className="w-4 h-4" />}
          />
        </CardApp>
      )}
    </div>
  );
}

export default SharePointSourceDetailPage;
