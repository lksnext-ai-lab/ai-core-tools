import { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
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
import { MESSAGES, errorMessage } from '../constants/messages';
import { sharepointApi } from '../services/sharepoint';
import type { SharePointSource, SharePointSyncStatus } from '../types/sharepoint';
import { LoadingState } from '../components/ui/LoadingState';
import { Spinner } from '../components/ui/Spinner';
import { Badge, type BadgeVariant } from '../components/ui/Badge';
import { Title } from '../components/ui/Title';
import BackgroundImage from '../components/ui/BackgroundImage';

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
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

function SharePointSourcesPage() {
  const { appId } = useParams<{ appId: string }>();
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
    } catch (_err) {
      setError('Failed to load SharePoint sources');
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
      title: MESSAGES.CONFIRM_DELETE_TITLE('SharePoint source'),
      message: `Are you sure you want to delete "${source.name}"? This will also delete all indexed content from the associated silo. This action cannot be undone.`,
      variant: 'danger',
      confirmLabel: 'Delete',
    });
    if (!ok) return;

    const result = await mutate(
      () => sharepointApi.deleteSource(Number(appId), source.id),
      {
        loading: MESSAGES.DELETING('SharePoint source'),
        success: MESSAGES.DELETED('SharePoint source'),
        error: (err) => errorMessage(err, MESSAGES.DELETE_FAILED('SharePoint source')),
      },
    );
    if (result === undefined) return;

    setSources((prev) => prev.filter((s) => s.id !== source.id));
  }

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <Title variant="titSecundario" titulo="SharePoint Sources" subtitulo="Sync documents from Microsoft SharePoint" />
        </div>
        <LoadingState variant="page" message="Loading sources..." />
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <Title variant="titSecundario" titulo="SharePoint Sources" subtitulo="Sync documents from Microsoft SharePoint" />
        </div>
        <Alert
          type="error"
          title="Error Loading Sources"
          message={error}
          onDismiss={() => { void loadSources(); }}
        />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <Title variant="titSecundario" titulo="SharePoint Sources" subtitulo="Sync documents from Microsoft SharePoint" />
        {canEdit && (
          <ButtonApp
            label="Add SharePoint Source"
            onClick={() => navigate(`/apps/${appId}/sharepoint/new`)}
            variant="primary"
            size="medium"
          />
        )}
      </div>

      {!canEdit && <ReadOnlyBanner userRole={userRole} minRole={AppRole.EDITOR} />}

      <Table
        data={sources}
        keyExtractor={(s) => s.id.toString()}
        columns={[
          {
            header: 'Name',
            render: (source) => (
              <div className="flex items-center">
                <div className="flex-shrink-0 h-10 w-10">
                  <BackgroundImage variant="marron" icon="Cloud" size={40} />
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
            header: 'Site / Drive',
            render: (source) => (
              <span className="text-xs text-fg-secondary dark:text-fg-secondary-dark">
                {source.site_name ?? source.site_id} / {source.drive_name ?? source.drive_id}
              </span>
            ),
          },
          {
            header: 'Status',
            render: (source) => {
              const badge = STATUS_BADGE[source.last_sync_status] ?? STATUS_BADGE.IDLE;
              return (
                <Badge
                  label={badge.label}
                  variant={badge.variant}
                  icon={source.last_sync_status === 'RUNNING' ? <Spinner size="xs" tone="current" /> : undefined}
                />
              );
            },
          },
          {
            header: 'Last Synced',
            render: (source) => (
              <span
                className="text-xs text-fg-secondary dark:text-fg-secondary-dark"
                title={source.last_synced_at ? new Date(source.last_synced_at).toLocaleString() : 'Never'}
              >
                {relativeTime(source.last_synced_at)}
              </span>
            ),
          },
          {
            header: 'Files',
            render: (source) => (
              <span className="text-xs text-fg-secondary dark:text-fg-secondary-dark">{source.file_count}</span>
            ),
          },
          {
            header: 'Actions',
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
                            label: isRunning ? 'Syncing...' : 'Sync now',
                            onClick: () => { void handleSync(source); },
                            icon: isRunning ? <Spinner size="sm" tone="current" /> : <RefreshCw className="w-4 h-4" />,
                            variant: 'primary' as const,
                            disabled: isRunning,
                          },
                          {
                            label: 'Edit',
                            onClick: () => navigate(`/apps/${appId}/sharepoint/${source.id}`),
                            icon: <Pencil className="w-4 h-4" />,
                            variant: 'primary' as const,
                          },
                        ]
                      : []),
                    ...(canDelete
                      ? [
                          {
                            label: 'Delete',
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
        emptyIcon={<Cloud className="w-10 h-10 text-gray-300" />}
        emptyMessage="No SharePoint Sources Yet"
        emptySubMessage="Add your first SharePoint source to start syncing documents."
        loading={loading}
      />

      {!loading && sources.length === 0 && canEdit && (
        <div className="text-center py-6">
          <ButtonApp
            label="Add Your First SharePoint Source"
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
