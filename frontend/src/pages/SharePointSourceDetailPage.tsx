import { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { RefreshCw, Trash2 } from 'lucide-react';
import Alert from '../components/ui/Alert';
import { TagInput } from '../components/ui/TagInput';
import { useAppRole } from '../hooks/useAppRole';
import { AppRole } from '../types/roles';
import { useConfirm } from '../contexts/ConfirmContext';
import { sharepointApi } from '../services/sharepoint';
import type { SharePointSourceDetail, SharePointSyncStatus } from '../types/sharepoint';
import { MESSAGES, errorMessage } from '../constants/messages';
import { useApiMutation } from '../hooks/useApiMutation';

const STATUS_BADGE: Record<SharePointSyncStatus, { label: string; className: string }> = {
  IDLE: { label: 'Idle', className: 'bg-gray-100 text-gray-600' },
  RUNNING: { label: 'Running', className: 'bg-blue-100 text-blue-700' },
  SUCCESS: { label: 'Success', className: 'bg-green-100 text-green-700' },
  PARTIAL: { label: 'Partial', className: 'bg-amber-100 text-amber-700' },
  ERROR: { label: 'Error', className: 'bg-red-100 text-red-700' },
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
    loadSource();
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
      <div className="flex items-center justify-center py-16">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-purple-600" />
        <span className="ml-2">Loading...</span>
      </div>
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
    <div className="max-w-3xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">{source.name}</h1>
          {source.description && <p className="text-gray-500">{source.description}</p>}
        </div>
        {canEdit && (
          <button
            onClick={() => { void handleSync(); }}
            disabled={isRunning}
            className="flex items-center gap-2 bg-purple-600 hover:bg-purple-700 disabled:opacity-50 text-white px-4 py-2 rounded-lg text-sm font-medium"
          >
            <RefreshCw className={`w-4 h-4 ${isRunning ? 'animate-spin' : ''}`} />
            {isRunning ? 'Syncing...' : 'Sync now'}
          </button>
        )}
      </div>

      {syncError && (
        <Alert type="error" title="Sync Error" message={syncError} onDismiss={() => setSyncError(null)} />
      )}

      {/* Sync status panel */}
      <div className="bg-white rounded-xl border border-gray-200 p-5">
        <h2 className="text-base font-semibold text-gray-900 mb-3">Sync Status</h2>
        <div className="flex flex-wrap gap-6">
          <div>
            <span className="text-xs text-gray-500">Status</span>
            <div className="mt-1">
              <span
                className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${statusBadge.className}`}
              >
                {isRunning && <RefreshCw className="w-3 h-3 animate-spin" />}
                {statusBadge.label}
              </span>
            </div>
          </div>
          <div>
            <span className="text-xs text-gray-500">Last synced</span>
            <p
              className="text-sm text-gray-700 mt-1"
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
            <span className="text-xs text-gray-500">Files indexed</span>
            <p className="text-sm text-gray-700 mt-1">{source.file_count}</p>
          </div>
        </div>
        {source.last_sync_error && (
          <div className="mt-3 p-3 bg-red-50 rounded-lg text-sm text-red-700">
            {source.last_sync_error}
          </div>
        )}
      </div>

      {/* General section */}
      {canEdit && (
        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <h2 className="text-base font-semibold text-gray-900 mb-3">General</h2>
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
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Name</label>
              <input
                type="text"
                value={generalName}
                onChange={(e) => setGeneralName(e.target.value)}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Description</label>
              <textarea
                value={generalDesc}
                onChange={(e) => setGeneralDesc(e.target.value)}
                rows={2}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div className="flex justify-end">
              <button
                onClick={() => { void handleSaveGeneral(); }}
                disabled={generalSaving}
                className="bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white px-4 py-2 rounded-lg text-sm"
              >
                {generalSaving ? 'Saving...' : 'Save'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* SharePoint connection section */}
      <div className="bg-white rounded-xl border border-gray-200 p-5">
        <h2 className="text-base font-semibold text-gray-900 mb-3">SharePoint Connection</h2>

        {/* Read-only site/drive info */}
        <div className="grid grid-cols-2 gap-4 mb-4">
          <div>
            <span className="text-xs text-gray-500">Site</span>
            <p className="text-sm text-gray-800 mt-0.5">{source.site_name ?? source.site_id}</p>
            {source.site_url && (
              <a
                href={source.site_url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs text-blue-600 hover:underline"
              >
                {source.site_url}
              </a>
            )}
          </div>
          <div>
            <span className="text-xs text-gray-500">Drive</span>
            <p className="text-sm text-gray-800 mt-0.5">{source.drive_name ?? source.drive_id}</p>
          </div>
        </div>

        {/* Editable credentials */}
        {canEdit && (
          <>
            <p className="text-xs text-gray-500 mb-3">
              Leave credential fields blank to keep the current values. All three fields must be
              provided together if you want to update credentials.
            </p>
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
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Tenant ID</label>
                <input
                  type="text"
                  value={credTenantId}
                  onChange={(e) => setCredTenantId(e.target.value)}
                  placeholder={`Current: ${source.tenant_id}`}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Client ID</label>
                <input
                  type="text"
                  value={credClientId}
                  onChange={(e) => setCredClientId(e.target.value)}
                  placeholder={`Current: ${source.client_id}`}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Client Secret</label>
                <input
                  type="password"
                  value={credSecret}
                  onChange={(e) => setCredSecret(e.target.value)}
                  placeholder="Leave blank to keep current"
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
              {(credTenantId || credClientId || credSecret) && (
                <p className="text-xs text-amber-600">
                  Credentials will be validated against Microsoft Graph on save.
                </p>
              )}
              <div className="flex justify-end">
                <button
                  onClick={() => { void handleSaveCredentials(); }}
                  disabled={credSaving || (!credTenantId && !credClientId && !credSecret)}
                  className="bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white px-4 py-2 rounded-lg text-sm"
                >
                  {credSaving ? 'Validating...' : 'Update Credentials'}
                </button>
              </div>
            </div>
          </>
        )}
      </div>

      {/* Indexing config section */}
      {canEdit && (
        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <h2 className="text-base font-semibold text-gray-900 mb-3">Indexing Config</h2>
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
              <button
                onClick={() => { void handleSaveFilters(); }}
                disabled={filtersSaving}
                className="bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white px-4 py-2 rounded-lg text-sm"
              >
                {filtersSaving ? 'Saving...' : 'Save Filters'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Danger zone */}
      {canDelete && (
        <div className="border border-red-200 rounded-xl p-5">
          <h2 className="text-base font-semibold text-red-700 mb-2">Danger Zone</h2>
          <p className="text-sm text-gray-600 mb-3">
            Deleting this source will permanently remove all indexed documents from the associated
            silo. This action cannot be undone.
          </p>
          <button
            onClick={() => { void handleDelete(); }}
            className="flex items-center gap-2 bg-red-600 hover:bg-red-700 text-white px-4 py-2 rounded-lg text-sm font-medium"
          >
            <Trash2 className="w-4 h-4" />
            Delete Source
          </button>
        </div>
      )}
    </div>
  );
}

export default SharePointSourceDetailPage;
