import { useState, useEffect, useCallback } from 'react';
import { Link, useParams, useNavigate } from 'react-router-dom';
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
import { MESSAGES, errorMessage } from '../constants/messages';
import type { MCPServerListItem } from '../core/types';
import { LoadingState } from '../components/ui/LoadingState';
import Alert from '../components/ui/Alert';
import Title from '../components/ui/Title';
import { SidePanel } from '../components/ui/SidePanel';
import MCPServerDetailPage from './MCPServerDetailPage';

function MCPServersPage() {
  const { appId } = useParams();
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
      setError(err instanceof Error ? err.message : 'Failed to load MCP servers');
      console.error('Error loading MCP servers:', err);
    } finally {
      setLoading(false);
    }
  }

  async function handleDelete(serverId: number): Promise<boolean> {
    if (!appId) return false;

    const target = servers.find((s) => s.server_id === serverId);
    const ok = await confirm({
      title: MESSAGES.CONFIRM_DELETE_TITLE('MCP server'),
      message: target
        ? `Are you sure you want to delete "${target.name}"? This action cannot be undone.`
        : MESSAGES.CONFIRM_DELETE_MESSAGE('MCP server'),
      variant: 'danger',
      confirmLabel: 'Delete',
    });
    if (!ok) return false;

    const result = await mutate(
      () => apiService.deleteMCPServer(Number.parseInt(appId), serverId),
      {
        loading: MESSAGES.DELETING('MCP server'),
        success: MESSAGES.DELETED('MCP server'),
        error: (err) => errorMessage(err, MESSAGES.DELETE_FAILED('MCP server')),
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
          <Title variant="titSecundario" titulo="MCP Servers"  subtitulo="Expose your agents as MCP tools for Claude Desktop, Cursor, and other clients" />
        </div>

        <LoadingState variant="page" message="Loading MCP servers..." />
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <Title variant="titSecundario" titulo="MCP Servers"  subtitulo="Expose your agents as MCP tools for Claude Desktop, Cursor, and other clients" />
        </div>

        <Alert
          type="error"
          title="Error Loading MCP Servers"
          message={(
            <>
              {error}
              <button type="button" onClick={() => loadServers()} className="mt-2 block underline">
                Try again
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
        <Title variant="titSecundario" titulo="MCP Servers"  subtitulo="Expose your agents as MCP tools for Claude Desktop, Cursor, and other clients" />
        {canEdit && (
          <ButtonLink
            label="Create MCP Server"
            to={`/apps/${appId}/mcp-servers/new`}
            variant="primary"
            size="control"
            icon={<Plus className="h-4 w-4" aria-hidden="true" />}
          />
        )}
      </div>

      {!canEdit && <ReadOnlyBanner userRole={userRole} minRole={AppRole.ADMINISTRATOR} />}

      {/* MCP Servers List */}
      {servers.length === 0 ? (
        <div className="bg-white rounded-lg shadow-md border p-8 text-center">
          <div className="text-6xl mb-4">-o-</div>
          <h3 className="text-lg font-semibold text-gray-900 mb-2">No MCP Servers Yet</h3>
          <p className="text-gray-600 mb-4">
            Create an MCP server to expose your agents as tools for external MCP clients like Claude Desktop and Cursor.
          </p>
          {canEdit && (
            <ButtonLink
              label="Create Your First MCP Server"
              to={`/apps/${appId}/mcp-servers/new`}
              variant="primary"
              size="large"
              icon={<Plus className="h-4 w-4" aria-hidden="true" />}
            />
          )}
        </div>
      ) : (
        <Table
          data={servers}
          keyExtractor={(server) => server.server_id.toString()}
          columns={[
            {
              header: 'Name',
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
              header: 'Status',
              render: (server) => (
                <Badge
                  label={server.is_active ? 'Active' : 'Inactive'}
                  variant={server.is_active ? 'success' : 'default'}
                />
              )
            },
            {
              header: 'Agents',
              render: (server) => (
                <span className="text-xs text-secondary dark:text-fg-secondary-dark">
                  {server.agent_count} {server.agent_count === 1 ? 'agent' : 'agents'}
                </span>
              )
            },
            {
              header: 'Endpoint',
              render: (server) => (
                <div className="flex items-center space-x-2">
                  <code className="text-xs text-fg-secondary dark:text-fg-secondary-dark truncate max-w-xs">
                    {server.endpoint_url}
                  </code>
                  <span title="Copy endpoint URL">
                    <ButtonApp
                      label={copiedId === server.server_id ? 'Done' : 'Copy'}
                      onClick={() => copyToClipboard(server.endpoint_url, server.server_id)}
                      variant="table"
                      size="small"
                    />
                  </span>
                </div>
              )
            },
            {
              header: 'Created',
              render: (server) => server.create_date ? new Date(server.create_date).toLocaleDateString() : 'N/A',
              className: 'px-6 py-4 whitespace-nowrap text-xs text-fg-secondary dark:text-fg-secondary-dark'
            },
            {
              header: 'Actions',
              headerClassName: 'px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider',
              className: 'px-6 py-4 whitespace-nowrap text-right text-sm font-medium',
              render: (server) => (
                <ActionDropdown
                  actions={[
                    {
                      label: 'View Details',
                      onClick: () => navigate(`/apps/${appId}/mcp-servers/${server.server_id}`),
                      icon: <Eye className="w-4 h-4" />,
                      variant: 'primary'
                    },
                    ...(canEdit ? [
                      {
                        label: 'Edit',
                        onClick: () => navigate(`/apps/${appId}/mcp-servers/${server.server_id}/edit`),
                        icon: <Pencil className="w-4 h-4" />,
                        variant: 'primary' as const
                      },
                      {
                        label: 'Delete',
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
          emptyIcon="-o-"
          emptyMessage="No MCP Servers Yet"
          emptySubMessage="Create an MCP server to expose your agents as tools."
          loading={loading}
        />
      )}

      {/* Server detail side panel — fixed wrapper that starts below the 56px (h-14) app header */}
      {selectedServerId !== null && (
        <div className="fixed inset-x-0 bottom-0 top-14 z-10 !mt-0">
          <SidePanel
            open
            side="right"
            onClose={handleClosePanel}
            title="MCP Servers"
            headerActions={(
              <span className="rounded-full bg-surface-hover px-2 py-0.5 text-[11px] normal-case tracking-normal text-fg-secondary dark:bg-surface-hover-dark dark:text-fg-secondary-dark">
                Vista de detalle
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
