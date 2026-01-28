import { useState, useEffect } from 'react';
import { Link, useParams, useNavigate } from 'react-router-dom';
import { apiService } from '../services/api';
import ActionDropdown from '../components/ui/ActionDropdown';
import Table from '../components/ui/Table';
import { useAppRole } from '../hooks/useAppRole';
import { AppRole } from '../types/roles';
import ReadOnlyBanner from '../components/ui/ReadOnlyBanner';
import type { MCPServerListItem } from '../core/types';

function MCPServersPage() {
  const { appId } = useParams();
  const { hasMinRole, userRole } = useAppRole(appId);
  const canEdit = hasMinRole(AppRole.ADMINISTRATOR);

  const [servers, setServers] = useState<MCPServerListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [copiedId, setCopiedId] = useState<number | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    loadServers();
  }, [appId]);

  async function loadServers() {
    if (!appId) return;

    try {
      setLoading(true);
      setError(null);
      const response = await apiService.getMCPServers(parseInt(appId));
      setServers(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load MCP servers');
      console.error('Error loading MCP servers:', err);
    } finally {
      setLoading(false);
    }
  }

  async function handleDelete(serverId: number) {
    if (!confirm('Are you sure you want to delete this MCP server? This action cannot be undone.')) {
      return;
    }

    if (!appId) return;

    try {
      await apiService.deleteMCPServer(parseInt(appId), serverId);
      setServers(servers.filter(s => s.server_id !== serverId));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete MCP server');
      console.error('Error deleting MCP server:', err);
    }
  }

  function copyToClipboard(text: string, serverId: number) {
    navigator.clipboard.writeText(text);
    setCopiedId(serverId);
    setTimeout(() => setCopiedId(null), 2000);
  }

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">MCP Servers</h1>
            <p className="text-gray-600">Expose your agents as MCP tools for Claude Desktop, Cursor, and other clients</p>
          </div>
        </div>

        <div className="flex items-center justify-center py-12">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-yellow-600"></div>
          <span className="ml-2">Loading MCP servers...</span>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">MCP Servers</h1>
            <p className="text-gray-600">Expose your agents as MCP tools for Claude Desktop, Cursor, and other clients</p>
          </div>
        </div>

        <div className="bg-red-50 border border-red-200 rounded-lg p-4">
          <div className="flex">
            <span className="text-red-400 text-xl mr-3">!</span>
            <div>
              <h3 className="text-sm font-medium text-red-800">Error Loading MCP Servers</h3>
              <p className="text-sm text-red-600 mt-1">{error}</p>
              <button
                onClick={() => loadServers()}
                className="mt-2 text-sm text-red-800 hover:text-red-900 underline"
              >
                Try again
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">MCP Servers</h1>
          <p className="text-gray-600">Expose your agents as MCP tools for Claude Desktop, Cursor, and other clients</p>
        </div>
        {canEdit && (
          <Link
            to={`/apps/${appId}/mcp-servers/new`}
            className="bg-yellow-600 hover:bg-yellow-700 text-white px-4 py-2 rounded-lg flex items-center"
          >
            <span aria-hidden="true" className="mr-2">+</span>
            <span>Create MCP Server</span>
          </Link>
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
            <Link
              to={`/apps/${appId}/mcp-servers/new`}
              className="bg-yellow-600 hover:bg-yellow-700 text-white px-6 py-2 rounded-lg inline-flex items-center"
            >
              <span aria-hidden="true" className="mr-2">+</span>
              <span>Create Your First MCP Server</span>
            </Link>
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
                    <div className="h-10 w-10 rounded-lg bg-purple-100 flex items-center justify-center">
                      <span className="text-purple-600 text-lg">-o-</span>
                    </div>
                  </div>
                  <div className="ml-4">
                    <div className="text-sm font-medium text-gray-900">
                      <Link
                        to={`/apps/${appId}/mcp-servers/${server.server_id}`}
                        className="text-sm font-medium text-gray-900 hover:text-blue-600 transition-colors"
                      >
                        {server.name}
                      </Link>
                    </div>
                    <div className="text-xs text-gray-500">
                      /{server.slug}
                    </div>
                  </div>
                </div>
              )
            },
            {
              header: 'Status',
              render: (server) => (
                <span className={`inline-flex px-2 py-1 text-xs font-semibold rounded-full ${
                  server.is_active
                    ? 'bg-green-100 text-green-800'
                    : 'bg-gray-100 text-gray-800'
                }`}>
                  {server.is_active ? 'Active' : 'Inactive'}
                </span>
              )
            },
            {
              header: 'Agents',
              render: (server) => (
                <span className="text-sm text-gray-900">
                  {server.agent_count} {server.agent_count === 1 ? 'agent' : 'agents'}
                </span>
              )
            },
            {
              header: 'Endpoint',
              render: (server) => (
                <div className="flex items-center space-x-2">
                  <code className="text-xs bg-gray-100 px-2 py-1 rounded truncate max-w-xs">
                    {server.endpoint_url}
                  </code>
                  <button
                    onClick={() => copyToClipboard(server.endpoint_url, server.server_id)}
                    className="text-gray-400 hover:text-gray-600"
                    title="Copy endpoint URL"
                  >
                    {copiedId === server.server_id ? (
                      <span className="text-green-500">Done</span>
                    ) : (
                      <span>Copy</span>
                    )}
                  </button>
                </div>
              )
            },
            {
              header: 'Created',
              render: (server) => server.create_date ? new Date(server.create_date).toLocaleDateString() : 'N/A',
              className: 'px-6 py-4 whitespace-nowrap text-sm text-gray-500'
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
                      icon: '(i)',
                      variant: 'primary'
                    },
                    ...(canEdit ? [
                      {
                        label: 'Edit',
                        onClick: () => navigate(`/apps/${appId}/mcp-servers/${server.server_id}/edit`),
                        icon: '*',
                        variant: 'primary' as const
                      },
                      {
                        label: 'Delete',
                        onClick: () => { void handleDelete(server.server_id); },
                        icon: 'x',
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
    </div>
  );
}

export default MCPServersPage;
