import { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Cloud, Pencil, Trash2, RefreshCw } from 'lucide-react';
import ActionDropdown from '../components/ui/ActionDropdown';
import Alert from '../components/ui/Alert';
import Table from '../components/ui/Table';
import ButtonApp from '../components/ui/ButtonApp';
import { useAppRole } from '../hooks/useAppRole';
import { AppRole } from '../types/roles';
import ReadOnlyBanner from '../components/ui/ReadOnlyBanner';
import { useConfirm } from '../contexts/ConfirmContext';
import { useApiMutation } from '../hooks/useApiMutation';
import { errorMessage } from '../constants/messages';
import { sharepointApi } from '../services/sharepoint';
import type { SharePointSource, SharePointSyncStatus } from '../types/sharepoint';
import { LoadingState } from '../components/ui/LoadingState';
import { Spinner } from '../components/ui/Spinner';
import { Badge, type BadgeVariant } from '../components/ui/Badge';
import { Title } from '../components/ui/Title';
import BackgroundImage from '../components/ui/BackgroundImage';

const STATUS_BADGE: Record<SharePointSyncStatus, { label: string; variant: BadgeVariant }> = {
  IDLE: { label: 'sharePointSourcesPage.statuses.idle', variant: 'default' },
  RUNNING: { label: 'sharePointSourcesPage.statuses.running', variant: 'info' },
  SUCCESS: { label: 'sharePointSourcesPage.statuses.success', variant: 'success' },
  PARTIAL: { label: 'sharePointSourcesPage.statuses.partial', variant: 'warning' },
  ERROR: { label: 'sharePointSourcesPage.statuses.error', variant: 'error' },
};

function SharePointSourcesPage() {
  const { appId } = useParams<{ appId: string }>();
  const { t, i18n } = useTranslation('common');
  const { hasMinRole, userRole } = useAppRole(appId);
  const canEdit = hasMinRole(AppRole.EDITOR);
  const canDelete = hasMinRole(AppRole.ADMINISTRATOR);
  const confirm = useConfirm();
  const mutate = useApiMutation();
  const navigate = useNavigate();

  const [sources, setSources] = useState<SharePointSource[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [syncingIds, setSyncingIds] = useState<Set<number>>(new Set());

  function formatRelativeTime(iso: string | null): string {
    if (!iso) return t('sharePointSourcesPage.relativeTime.never');
    const diff = Date.now() - new Date(iso).getTime();
    const minutes = Math.floor(diff / 60000);
    if (minutes < 1) return t('sharePointSourcesPage.relativeTime.justNow');
    if (minutes < 60) return t('sharePointSourcesPage.relativeTime.minutesAgo', { count: minutes });
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return t('sharePointSourcesPage.relativeTime.hoursAgo', { count: hours });
    const days = Math.floor(hours / 24);
    return t('sharePointSourcesPage.relativeTime.daysAgo', { count: days });
  }

  useEffect(() => {
    void loadSources();
  }, [appId]);

  async function loadSources() {
    if (!appId) return;
    try {
      setLoading(true);
      setError(null);
      const data = await sharepointApi.listSources(Number(appId));
      setSources(data || []);
    } catch (err) {
      setError(errorMessage(err, t('sharePointSourcesPage.loadFailed')));
      setSources([]);
    } finally {
      setLoading(false);
    }
  }

  async function handleSync(source: SharePointSource) {
    if (!appId) return;
    setSyncingIds((prev) => new Set(prev).add(source.id));
    try {
      await sharepointApi.triggerSync(Number(appId), source.id);
      setSources((prev) =>
        prev.map((s) =>
          s.id === source.id ? { ...s, last_sync_status: 'RUNNING' as const } : s,
        ),
      );
    } catch (err: any) {
      // 409 means already syncing — update local status
      if (err?.message?.includes('409') || err?.message?.toLowerCase().includes('already')) {
        setSources((prev) =>
          prev.map((s) =>
            s.id === source.id ? { ...s, last_sync_status: 'RUNNING' as const } : s,
          ),
        );
      }
    } finally {
      setSyncingIds((prev) => {
        const next = new Set(prev);
        next.delete(source.id);
        return next;
      });
    }
  }

  async function handleDelete(source: SharePointSource) {
    if (!appId) return;
    const ok = await confirm({
      title: t('sharePointSourcesPage.confirmDeleteTitle'),
      message: t('sharePointSourcesPage.confirmDeleteMessage', { name: source.name }),
      variant: 'danger',
      confirmLabel: t('sharePointSourcesPage.actions.delete'),
    });
    if (!ok) return;

    const result = await mutate(
      () => sharepointApi.deleteSource(Number(appId), source.id),
      {
        loading: t('sharePointSourcesPage.notifications.deleting'),
        success: t('sharePointSourcesPage.notifications.deleted'),
        error: (err) => errorMessage(err, t('sharePointSourcesPage.notifications.deleteFailed')),
      },
    );
    if (result === undefined) return;

    setSources((prev) => prev.filter((s) => s.id !== source.id));
  }

  if (loading) {
    return (
      <div className="mx-auto max-w-4xl space-y-6">
        <div className="flex items-center justify-between">
          <Title variant="titSecundario" titulo={t('sharePointSourcesPage.title')} subtitulo={t('sharePointSourcesPage.subtitle')} />
        </div>
        <LoadingState variant="page" message={t('sharePointSourcesPage.loading')} />
      </div>
    );
  }

  if (error) {
    return (
      <div className="mx-auto max-w-4xl space-y-6">
        <div className="flex items-center justify-between">
          <Title variant="titSecundario" titulo={t('sharePointSourcesPage.title')} subtitulo={t('sharePointSourcesPage.subtitle')} />
        </div>
        <Alert
          type="error"
          title={t('sharePointSourcesPage.loadErrorTitle')}
          message={error}
          onDismiss={() => { void loadSources(); }}
        />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <Title variant="titSecundario" titulo={t('sharePointSourcesPage.title')} subtitulo={t('sharePointSourcesPage.subtitle')} />
        {canEdit && (
          <ButtonApp
            label={t('sharePointSourcesPage.actions.addSource')}
            onClick={() => navigate(`/apps/${appId}/sharepoint/new`)}
            variant="primary"
            size="medium"
          />
        )}
      </div>

      {!canEdit && <ReadOnlyBanner userRole={userRole} minRole={AppRole.EDITOR} />}

      <Table
        data={sources}
        stickyEdgeColumns
        keyExtractor={(s) => s.id.toString()}
        columns={[
          {
            header: t('sharePointSourcesPage.columns.name'),
            render: (source) => (
              <div className="flex items-center">
                <div className="flex-shrink-0 h-10 w-10">
                  <BackgroundImage variant="marron" icon={Cloud} size={40} />
                </div>
                <div className="ml-4">
                  <Link
                    to={`/apps/${appId}/sharepoint/${source.id}`}
                    className="text-sm font-medium text-fg dark:text-fg-dark"
                  >
                    {source.name}
                  </Link>
                  {source.description && (
                    <div className="text-xs text-fg-secondary dark:text-fg-secondary-dark">{source.description}</div>
                  )}
                </div>
              </div>
            ),
          },
          {
            header: t('sharePointSourcesPage.columns.siteDrive'),
            render: (source) => (
              <span className="text-xs text-fg-secondary dark:text-fg-secondary-dark">
                {source.site_name ?? source.site_id} / {source.drive_name ?? source.drive_id}
              </span>
            ),
          },
          {
            header: t('sharePointSourcesPage.columns.status'),
            render: (source) => {
              const badge = STATUS_BADGE[source.last_sync_status] ?? STATUS_BADGE.IDLE;
              return (
                <Badge
                  label={t(badge.label)}
                  variant={badge.variant}
                  icon={source.last_sync_status === 'RUNNING' ? <Spinner size="xs" tone="current" /> : undefined}
                />
              );
            },
          },
          {
            header: t('sharePointSourcesPage.columns.lastSynced'),
            render: (source) => (
              <span
                className="text-xs text-fg-secondary dark:text-fg-secondary-dark"
                title={source.last_synced_at ? new Date(source.last_synced_at).toLocaleString(i18n.resolvedLanguage) : t('sharePointSourcesPage.relativeTime.never')}
              >
                {formatRelativeTime(source.last_synced_at)}
              </span>
            ),
          },
          {
            header: t('sharePointSourcesPage.columns.files'),
            render: (source) => (
              <span className="text-xs text-fg-secondary dark:text-fg-secondary-dark">{source.file_count}</span>
            ),
          },
          {
            header: t('sharePointSourcesPage.columns.actions'),
            sticky: 'right',
            headerClassName: 'px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider',
            className: 'px-6 py-4 whitespace-nowrap text-right text-sm font-medium relative',
            render: (source) => {
              const isRunning =
                source.last_sync_status === 'RUNNING' || syncingIds.has(source.id);
              return (
                <ActionDropdown
                  actions={[
                    ...(canEdit
                      ? [
                          {
                            label: t(isRunning ? 'sharePointSourcesPage.actions.syncing' : 'sharePointSourcesPage.actions.syncNow'),
                            onClick: () => { void handleSync(source); },
                            icon: isRunning ? <Spinner size="sm" tone="current" /> : <RefreshCw className="w-4 h-4" />,
                            variant: 'primary' as const,
                            disabled: isRunning,
                          },
                          {
                            label: t('sharePointSourcesPage.actions.edit'),
                            onClick: () => navigate(`/apps/${appId}/sharepoint/${source.id}`),
                            icon: <Pencil className="w-4 h-4" />,
                            variant: 'primary' as const,
                          },
                        ]
                      : []),
                    ...(canDelete
                      ? [
                          {
                            label: t('sharePointSourcesPage.actions.delete'),
                            onClick: () => { void handleDelete(source); },
                            icon: <Trash2 className="w-4 h-4" />,
                            variant: 'danger' as const,
                          },
                        ]
                      : []),
                  ]}
                  size="sm"
                />
              );
            },
          },
        ]}
        emptyIcon={<BackgroundImage icon={Cloud} size={64} iconSize={32} />}
        emptyMessage={t('sharePointSourcesPage.emptyTitle')}
        emptySubMessage={t('sharePointSourcesPage.emptyDescription')}
        loading={loading}
      />

      {!loading && sources.length === 0 && canEdit && (
        <div className="text-center py-6">
          <ButtonApp
            label={t('sharePointSourcesPage.actions.addFirstSource')}
            onClick={() => navigate(`/apps/${appId}/sharepoint/new`)}
            variant="primary"
            size="medium"
          />
        </div>
      )}
    </div>
  );


  
}

export default SharePointSourcesPage;
