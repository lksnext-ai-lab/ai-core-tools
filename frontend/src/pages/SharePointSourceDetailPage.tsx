import { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { RefreshCw, SquareArrowOutUpRight, Trash2 } from 'lucide-react';
import Alert from '../components/ui/Alert';
import { TagInput } from '../components/ui/TagInput';
import { useAppRole } from '../hooks/useAppRole';
import { AppRole } from '../types/roles';
import { useConfirm } from '../contexts/ConfirmContext';
import { sharepointApi } from '../services/sharepoint';
import type { SharePointSourceDetail, SharePointSyncStatus } from '../types/sharepoint';
import { errorMessage } from '../constants/messages';
import { useApiMutation } from '../hooks/useApiMutation';
import { LoadingState } from '../components/ui/LoadingState';
import { ButtonApp } from '../components/ui/ButtonApp';
import { FormField, FormTextArea } from '../components/ui/FormField';
import { Spinner } from '../components/ui/Spinner';
import { Badge, type BadgeVariant } from '../components/ui/Badge';
import Title from '../components/ui/Title';
import CardApp from '../components/ui/CardApp';

const STATUS_BADGE: Record<SharePointSyncStatus, { label: string; variant: BadgeVariant }> = {
  IDLE: { label: 'sharePointSourcesPage.statuses.idle', variant: 'default' },
  RUNNING: { label: 'sharePointSourcesPage.statuses.running', variant: 'info' },
  SUCCESS: { label: 'sharePointSourcesPage.statuses.success', variant: 'success' },
  PARTIAL: { label: 'sharePointSourcesPage.statuses.partial', variant: 'warning' },
  ERROR: { label: 'sharePointSourcesPage.statuses.error', variant: 'error' },
};

function SharePointSourceDetailPage() {
  const { appId, sourceId } = useParams<{ appId: string; sourceId: string }>();
  const navigate = useNavigate();
  const { t, i18n } = useTranslation('common');
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

  function formatRelativeTime(iso: string | null): string {
    if (!iso) return t('sharePointSourcesPage.relativeTime.never');
    const diff = Date.now() - new Date(iso).getTime();
    const minutes = Math.floor(diff / 60000);
    if (minutes < 1) return t('sharePointSourcesPage.relativeTime.justNow');
    if (minutes < 60) return t('sharePointSourcesPage.relativeTime.minutesAgo', { count: minutes });
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return t('sharePointSourcesPage.relativeTime.hoursAgo', { count: hours });
    return t('sharePointSourcesPage.relativeTime.daysAgo', { count: Math.floor(hours / 24) });
  }

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
      if (!silent) setError(errorMessage(err, t('sharePointSourceDetailPage.loadFailed')));
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
      setGeneralError(errorMessage(err, t('sharePointSourceDetailPage.errors.saveGeneral')));
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
      setCredError(errorMessage(err, t('sharePointSourceDetailPage.errors.updateCredentials')));
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
      setFiltersError(errorMessage(err, t('sharePointSourceDetailPage.errors.saveFilters')));
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
        setSyncError(msg || t('sharePointSourceDetailPage.errors.triggerSync'));
      }
    } finally {
      setSyncing(false);
    }
  }

  async function handleDelete() {
    if (!appId || !sourceId) return;
    const ok = await confirm({
      title: t('sharePointSourcesPage.confirmDeleteTitle'),
      message: t('sharePointSourceDetailPage.confirmDeleteMessage'),
      variant: 'danger',
      confirmLabel: t('sharePointSourcesPage.actions.delete'),
    });
    if (!ok) return;

    const result = await mutate(
      () => sharepointApi.deleteSource(Number(appId), Number(sourceId)),
      {
        loading: t('sharePointSourcesPage.notifications.deleting'),
        success: t('sharePointSourcesPage.notifications.deleted'),
        error: (err) => errorMessage(err, t('sharePointSourcesPage.notifications.deleteFailed')),
      },
    );
    if (result === undefined) return;
    navigate(`/apps/${appId}/sharepoint`);
  }

  if (loading) {
    return (
      <LoadingState variant="page" message={t('sharePointSourceDetailPage.loading')} />
    );
  }

  if (error || !source) {
    return (
      <Alert
        type="error"
        title={t('sharePointSourceDetailPage.loadErrorTitle')}
        message={error ?? t('sharePointSourceDetailPage.notFound')}
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
            label={t(isRunning ? 'sharePointSourcesPage.actions.syncing' : 'sharePointSourcesPage.actions.syncNow')}
            onClick={() => { void handleSync(); }}
            loading={isRunning}
            icon={<RefreshCw className="w-4 h-4" />}
          />
        )}
      </div>

      {syncError && (
        <Alert type="error" title={t('sharePointSourceDetailPage.syncErrorTitle')} message={syncError} onDismiss={() => setSyncError(null)} />
      )}

      {/* Sync status panel */}
      <CardApp className="p-5">
        <h3 className="text-lg font-semibold text-fg dark:text-fg-dark mb-3">{t('sharePointSourceDetailPage.sections.syncStatus')}</h3>
        <div className="flex flex-wrap justify-between gap-6">
          <div>
            <span className="text-xs text-fg-secondary dark:text-fg-secondary-dark">{t('sharePointSourceDetailPage.fields.status')}</span>
            <div className="mt-1">
              <Badge
                label={t(statusBadge.label)}
                variant={statusBadge.variant}
                icon={source.last_sync_status === 'RUNNING' ? <Spinner size="xs" tone="current" /> : undefined}
              />
            </div>
          </div>
          <div>
            <span className="text-xs text-fg-secondary dark:text-fg-secondary-dark">{t('sharePointSourceDetailPage.fields.lastSynced')}</span>
            <p
              className="text-sm text-fg dark:text-fg-dark mt-1"
              title={
                source.last_synced_at
                  ? new Date(source.last_synced_at).toLocaleString(i18n.resolvedLanguage)
                  : t('sharePointSourcesPage.relativeTime.never')
              }
            >
              {formatRelativeTime(source.last_synced_at)}
            </p>
          </div>
          <div>
            <span className="text-xs text-fg-secondary dark:text-fg-secondary-dark">{t('sharePointSourceDetailPage.fields.filesIndexed')}</span>
            <p className="text-sm text-fg dark:text-fg-dark mt-1">{source.file_count}</p>
          </div>
        </div>
        {source.last_sync_error && (
          <Alert
            type="error"
            title={t('sharePointSourceDetailPage.syncErrorTitle')}
            message={source.last_sync_error}
            className="mt-3"
          />
        )}
      </CardApp>

      {/* General section */}
      {canEdit && (
        <CardApp className="p-5">
          <h3 className="text-lg font-semibold text-fg dark:text-fg-dark mb-3">{t('sharePointSourceDetailPage.sections.general')}</h3>
          {generalError && (
            <Alert
              type="error"
              title={t('sharePointSourceDetailPage.errors.saveFailedTitle')}
              message={generalError}
              onDismiss={() => setGeneralError(null)}
              className="mb-3"
            />
          )}
          <div className="space-y-3">
            <FormField
              label={t('sharePointSourceDetailPage.fields.name')}
              id="general-name"
              value={generalName}
              onChange={(e) => setGeneralName(e.target.value)}
            />
            <FormTextArea
              label={t('sharePointSourceDetailPage.fields.description')}
              id="general-description"
              value={generalDesc}
              onChange={(e) => setGeneralDesc(e.target.value)}
              rows={2}
            />
            <div className="flex justify-end">
              <ButtonApp
                label={t(generalSaving ? 'sharePointSourceDetailPage.actions.saving' : 'sharePointSourceDetailPage.actions.save')}
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
        <h3 className="text-lg font-semibold text-fg dark:text-fg-dark mb-3">{t('sharePointSourceDetailPage.sections.connection')}</h3>

        {/* Read-only site/drive info */}
        <div className="grid grid-cols-2 gap-4 mb-4">
          <div>
            <span className="text-xs text-fg-secondary dark:text-fg-secondary-dark">{t('sharePointSourceDetailPage.fields.site')}</span>
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
            <span className="text-xs text-fg dark:text-fg-dark">{t('sharePointSourceDetailPage.fields.drive')}</span>
            <p className="text-sm text-fg dark:text-fg-dark mt-0.5">{source.drive_name ?? source.drive_id}</p>
          </div>
        </div>

        {/* Editable credentials */}
        {canEdit && (
          <>
            {credError && (
              <Alert
                type="error"
                title={t('sharePointSourceDetailPage.errors.updateCredentialsTitle')}
                message={credError}
                onDismiss={() => setCredError(null)}
                className="mb-3"
              />
            )}
            <div className="space-y-3">
              <FormField
                label={t('sharePointSourceDetailPage.fields.tenantId')}
                id="tenant-id"
                value={credTenantId}
                onChange={(e) => setCredTenantId(e.target.value)}
                placeholder={t('sharePointSourceDetailPage.fields.currentCredential', { value: source.tenant_id })}
                helpText={t('sharePointSourceDetailPage.help.credentials')}
              />
              <FormField
                label={t('sharePointSourceDetailPage.fields.clientId')}
                id="client-id"
                value={credClientId}
                onChange={(e) => setCredClientId(e.target.value)}
                placeholder={t('sharePointSourceDetailPage.fields.currentCredential', { value: source.client_id })}
              />
              <FormField
                label={t('sharePointSourceDetailPage.fields.clientSecret')}
                id="client-secret"
                type="password"
                value={credSecret}
                onChange={(e) => setCredSecret(e.target.value)}
                placeholder={t('sharePointSourceDetailPage.fields.keepCurrent')}
                helpText={(credTenantId || credClientId || credSecret)
                  ? t('sharePointSourceDetailPage.help.validateCredentials')
                  : undefined}
              />
              <div className="flex justify-end">
                <ButtonApp
                  label={t(credSaving ? 'sharePointSourceDetailPage.actions.validating' : 'sharePointSourceDetailPage.actions.updateCredentials')}
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
          <h3 className="text-lg font-semibold text-fg dark:text-fg-dark mb-3">{t('sharePointSourceDetailPage.sections.indexingConfig')}</h3>
          {filtersError && (
            <Alert
              type="error"
              title={t('sharePointSourceDetailPage.errors.saveFailedTitle')}
              message={filtersError}
              onDismiss={() => setFiltersError(null)}
              className="mb-3"
            />
          )}
          <div className="space-y-3">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                {t('sharePointSourceDetailPage.fields.fileExtensionFilters')}
              </label>
              <TagInput
                tags={fileExtensions}
                onChange={setFileExtensions}
                maxTags={20}
                placeholder={t('sharePointSourceDetailPage.fields.fileExtensionsPlaceholder')}
              />
              <p className="text-xs text-gray-500 mt-1">{t('sharePointSourceDetailPage.help.emptyExtensions')}</p>
            </div>
            <div className="flex justify-end">
              <ButtonApp
                label={t(filtersSaving ? 'sharePointSourceDetailPage.actions.saving' : 'sharePointSourceDetailPage.actions.saveFilters')}
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
          <h3 className="text-lg font-semibold text-error mb-3">{t('sharePointSourceDetailPage.sections.dangerZone')}</h3>
          <p className="text-sm text-gray-600 mb-3">
            {t('sharePointSourceDetailPage.help.deleteWarning')}
          </p>
          <ButtonApp
            label={t('sharePointSourceDetailPage.actions.deleteSource')}
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
