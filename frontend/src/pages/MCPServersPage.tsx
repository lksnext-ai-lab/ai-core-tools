import { useState, useEffect, useCallback } from 'react';
import { Link, useParams, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Eye, Pencil, Plus, Trash2, Plug } from 'lucide-react';
import { apiService } from '../services/api';
import ActionDropdown from '../components/ui/ActionDropdown';
import Table from '../components/ui/Table';
import ButtonApp from '../components/ui/ButtonApp';
import ButtonLink from '../components/ui/ButtonLink';
import BackgroundImage from '../components/ui/BackgroundImage';
import Badge from '../components/ui/Badge';
import { useAppRole } from '../hooks/useAppRole';
import { AppRole } from '../types/roles';
import ReadOnlyBanner from '../components/ui/ReadOnlyBanner';
import { useConfirm } from '../contexts/ConfirmContext';
import { useApiMutation } from '../hooks/useApiMutation';
import { errorMessage } from '../constants/messages';
import type { MCPServerListItem } from '../core/types';
import { LoadingState } from '../components/ui/LoadingState';
import Alert from '../components/ui/Alert';
import Title from '../components/ui/Title';
import { SidePanel } from '../components/ui/SidePanel';
import MCPServerDetailPage from './MCPServerDetailPage';

function MCPServersPage() {
  const { appId } = useParams();
  const { t, i18n } = useTranslation('common');
  const { hasMinRole, userRole } = useAppRole(appId);
  const canEdit = hasMinRole(AppRole.ADMINISTRATOR);
  const confirm = useConfirm();
  const mutate = useApiMutation();

  const [servers, setServers] = useState<MCPServerListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [copiedId, setCopiedId] = useState<number | null>(null);
  const [selectedServerId, setSelectedServerId] = useState<number | null>(null);
  const handleClosePanel = useCallback(() => setSelectedServerId(null), []);
  const navigate = useNavigate();

  useEffect(() => {
    void loadServers();
  }, [appId]);

  async function loadServers() {
    if (!appId) return;

    try {
      setLoading(true);
      setError(null);
      const response = await apiService.getMCPServers(Number.parseInt(appId));
      setServers(response);
    } catch (err) {
      setError(errorMessage(err, t('mcpServersPage.loadFailed')));
      console.error('Error loading MCP servers:', err);
    } finally {
      setLoading(false);
    }
  }

  async function handleDelete(serverId: number): Promise<boolean> {
    if (!appId) return false;

    const target = servers.find((s) => s.server_id === serverId);
    const ok = await confirm({
      title: t('mcpServersPage.confirmDeleteTitle'),
      message: target
        ? t('mcpServersPage.confirmDeleteMessage', { name: target.name })
        : t('mcpServersPage.confirmDeleteFallback'),
      variant: 'danger',
      confirmLabel: t('mcpServersPage.actions.delete'),
    });
    if (!ok) return false;

    const result = await mutate(
      () => apiService.deleteMCPServer(Number.parseInt(appId), serverId),
      {
        loading: t('mcpServersPage.notifications.deleting'),
        success: t('mcpServersPage.notifications.deleted'),
        error: (err) => errorMessage(err, t('mcpServersPage.notifications.deleteFailed')),
      },
    );
    if (result === undefined) return false;

    setServers(servers.filter((s) => s.server_id !== serverId));
    return true;
  }

  function copyToClipboard(text: string, serverId: number) {
    // Only show "copied" once the clipboard write actually succeeded (it can be
    // rejected, e.g. without clipboard permission or when the page lacks focus).
    navigator.clipboard.writeText(text).then(() => {
      setCopiedId(serverId);
      setTimeout(() => setCopiedId(null), 2000);
    }).catch(() => {
      // ignore: nothing was copied, so no confirmation is shown
    });
  }

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">  
          <Title variant="titSecundario" titulo={t('mcpServersPage.title')} subtitulo={t('mcpServersPage.subtitle')} />
        </div>

        <LoadingState variant="page" message={t('mcpServersPage.loading')} />
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <Title variant="titSecundario" titulo={t('mcpServersPage.title')} subtitulo={t('mcpServersPage.subtitle')} />
        </div>

        <Alert
          type="error"
          title={t('mcpServersPage.loadErrorTitle')}
          message={(
            <>
              {error}
              <button type="button" onClick={() => loadServers()} className="mt-2 block underline">
                {t('mcpServersPage.tryAgain')}
              </button>
            </>
          )}
        />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <Title variant="titSecundario" titulo={t('mcpServersPage.title')} subtitulo={t('mcpServersPage.subtitle')} />
        {canEdit && (
          <ButtonLink
            label={t('mcpServersPage.actions.create')}
            to={`/apps/${appId}/mcp-servers/new`}
            variant="primary"
            size="control"
            icon={<Plus className="h-4 w-4" aria-hidden="true" />}
          />
        )}
      </div>

      {!canEdit && <ReadOnlyBanner userRole={userRole} minRole={AppRole.ADMINISTRATOR} />}

      {/* MCP Servers List */}
      <Table
          data={servers}
          stickyEdgeColumns
          keyExtractor={(server) => server.server_id.toString()}
          columns={[
            {
              header: t('mcpServersPage.columns.name'),
              render: (server) => (
                <div className="flex items-center">
                  <div className="flex-shrink-0 h-10 w-10">
                    <BackgroundImage icon={Plug} size={40} iconSize={20} variant="marron" />
                  </div>
                  <div className="ml-4">
                    <div className="text-sm font-medium text-gray-900">
                      <Link
                        to={`/apps/${appId}/mcp-servers/${server.server_id}`}
                        className="text-sm font-medium text-fg dark:text-fg-dark"
                        onClick={(event) => {
                          // Keep native behaviour for new tab / new window clicks.
                          if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
                          event.preventDefault();
                          setSelectedServerId(server.server_id);
                        }}
                      >
                        {server.name}
                      </Link>
                    </div>
                    <div className="text-xs text-fg-tertiary dark:text-fg-tertiary-dark">
                      /{server.slug}
                    </div>
                  </div>
                </div>
              )
            },
            {
              header: t('mcpServersPage.columns.status'),
              render: (server) => (
                <Badge
                  label={t(server.is_active ? 'mcpServersPage.statuses.active' : 'mcpServersPage.statuses.inactive')}
                  variant={server.is_active ? 'success' : 'default'}
                />
              )
            },
            {
              header: t('mcpServersPage.columns.agents'),
              render: (server) => (
                <span className="text-xs text-secondary dark:text-fg-secondary-dark">
                  {t('mcpServersPage.agentCount', { count: server.agent_count })}
                </span>
              )
            },
            {
              header: t('mcpServersPage.columns.endpoint'),
              render: (server) => (
                <div className="flex items-center space-x-2">
                  <code className="text-xs text-fg-secondary dark:text-fg-secondary-dark truncate max-w-xs">
                    {server.endpoint_url}
                  </code>
                  <span title={t('mcpServersPage.copyEndpoint')}>
                    <ButtonApp
                      label={t(copiedId === server.server_id ? 'mcpServersPage.actions.copied' : 'mcpServersPage.actions.copy')}
                      onClick={() => copyToClipboard(server.endpoint_url, server.server_id)}
                      variant="table"
                      size="small"
                    />
                  </span>
                </div>
              )
            },
            {
              header: t('mcpServersPage.columns.created'),
              render: (server) => server.create_date ? new Date(server.create_date).toLocaleDateString(i18n.resolvedLanguage) : t('mcpServersPage.notAvailable'),
              className: 'px-6 py-4 whitespace-nowrap text-xs text-fg-secondary dark:text-fg-secondary-dark'
            },
            {
              header: t('mcpServersPage.columns.actions'),
              sticky: 'right',
              headerClassName: 'px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider',
              className: 'px-6 py-4 whitespace-nowrap text-right text-sm font-medium',
              render: (server) => (
                <ActionDropdown
                  actions={[
                    {
                      label: t('mcpServersPage.actions.viewDetails'),
                      onClick: () => navigate(`/apps/${appId}/mcp-servers/${server.server_id}`),
                      icon: <Eye className="w-4 h-4" />,
                      variant: 'primary'
                    },
                    ...(canEdit ? [
                      {
                        label: t('mcpServersPage.actions.edit'),
                        onClick: () => navigate(`/apps/${appId}/mcp-servers/${server.server_id}/edit`),
                        icon: <Pencil className="w-4 h-4" />,
                        variant: 'primary' as const
                      },
                      {
                        label: t('mcpServersPage.actions.delete'),
                        onClick: () => { void handleDelete(server.server_id); },
                        icon: <Trash2 className="w-4 h-4" />,
                        variant: 'danger' as const
                      }
                    ] : [])
                  ]}
                  size="sm"
                />
              )
            }
          ]}
          emptyIcon={<BackgroundImage icon={Plug} size={64} iconSize={32} />}
          emptyMessage={t('mcpServersPage.emptyTitle')}
          emptySubMessage={t('mcpServersPage.emptyDescription')}
          loading={loading}
      />

      {!loading && canEdit && servers.length === 0 && (
        <div className="text-center py-6">
          <ButtonLink
            label={t('mcpServersPage.actions.createFirst')}
            to={`/apps/${appId}/mcp-servers/new`}
            variant="primary"
            size="medium"
            icon={<Plus className="h-4 w-4" aria-hidden="true" />}
          />
        </div>
      )}

      {/* Server detail side panel — fixed wrapper that starts below the 56px (h-14) app header */}
      {selectedServerId !== null && (
        <div className="fixed inset-x-0 bottom-0 top-14 z-30 !mt-0">
          <SidePanel
            open
            side="right"
            onClose={handleClosePanel}
            title={t('mcpServersPage.title')}
            headerActions={(
              <span className="rounded-full bg-surface-hover px-2 py-0.5 text-[11px] normal-case tracking-normal text-fg-secondary dark:bg-surface-hover-dark dark:text-fg-secondary-dark">
                {t('mcpServersPage.detailView')}
              </span>
            )}
            widthClassName="w-[640px] max-w-full"
          >
            <MCPServerDetailPage
              key={selectedServerId}
              serverId={selectedServerId}
              variant="panel"
              onDelete={() => {
                void handleDelete(selectedServerId).then((deleted) => {
                  if (deleted) handleClosePanel();
                });
              }}
            />
          </SidePanel>
        </div>
      )}
    </div>
  );
}

export default MCPServersPage;
