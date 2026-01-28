import { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { apiService } from '../services/api';
import { useAppRole } from '../hooks/useAppRole';
import { AppRole } from '../types/roles';
import type { MCPServer } from '../core/types';

function MCPServerDetailPage() {
  const { appId, serverId } = useParams();
  const navigate = useNavigate();
  const { hasMinRole } = useAppRole(appId);
  const canEdit = hasMinRole(AppRole.ADMINISTRATOR);

  const [server, setServer] = useState<MCPServer | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [copiedField, setCopiedField] = useState<string | null>(null);

  useEffect(() => {
    if (!appId || !serverId) return;
    void loadServer();
  }, [appId, serverId]);

  async function loadServer() {
    if (!appId || !serverId) return;

    try {
      setLoading(true);
      setError(null);
      const response = await apiService.getMCPServer(parseInt(appId), parseInt(serverId));
      setServer(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load MCP server');
      console.error('Error loading MCP server:', err);
    } finally {
      setLoading(false);
    }
  }

  async function handleDelete() {
    if (!confirm('Are you sure you want to delete this MCP server? This action cannot be undone.')) {
      return;
    }

    if (!appId || !serverId) return;

    try {
      await apiService.deleteMCPServer(parseInt(appId), parseInt(serverId));
      navigate(`/apps/${appId}/mcp-servers`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete MCP server');
    }
  }

  function copyToClipboard(text: string, field: string) {
    navigator.clipboard.writeText(text);
    setCopiedField(field);
    setTimeout(() => setCopiedField(null), 2000);
  }

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">MCP Server Details</h1>
            <p className="text-gray-600">Loading...</p>
          </div>
        </div>

        <div className="flex items-center justify-center py-12">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-yellow-600"></div>
          <span className="ml-2">Loading MCP server...</span>
        </div>
      </div>
    );
  }

  if (error || !server) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">MCP Server Details</h1>
          </div>
        </div>

        <div className="bg-red-50 border border-red-200 rounded-lg p-4">
          <div className="flex">
            <span className="text-red-400 text-xl mr-3">!</span>
            <div>
              <h3 className="text-sm font-medium text-red-800">Error</h3>
              <p className="text-sm text-red-600 mt-1">{error || 'MCP server not found'}</p>
              <Link
                to={`/apps/${appId}/mcp-servers`}
                className="mt-2 text-sm text-red-800 hover:text-red-900 underline inline-block"
              >
                Back to MCP Servers
              </Link>
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
          <div className="flex items-center space-x-3">
            <h1 className="text-2xl font-bold text-gray-900">{server.name}</h1>
            <span className={`inline-flex px-2 py-1 text-xs font-semibold rounded-full ${
              server.is_active
                ? 'bg-green-100 text-green-800'
                : 'bg-gray-100 text-gray-800'
            }`}>
              {server.is_active ? 'Active' : 'Inactive'}
            </span>
          </div>
          <p className="text-gray-600">{server.description || 'No description'}</p>
        </div>
        <div className="flex space-x-2">
          <Link
            to={`/apps/${appId}/mcp-servers`}
            className="px-4 py-2 text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-lg"
          >
            Back
          </Link>
          {canEdit && (
            <>
              <Link
                to={`/apps/${appId}/mcp-servers/${serverId}/edit`}
                className="px-4 py-2 text-white bg-yellow-600 hover:bg-yellow-700 rounded-lg"
              >
                Edit
              </Link>
              <button
                onClick={handleDelete}
                className="px-4 py-2 text-white bg-red-600 hover:bg-red-700 rounded-lg"
              >
                Delete
              </button>
            </>
          )}
        </div>
      </div>

      {/* Server Info */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Basic Info Card */}
        <div className="bg-white rounded-lg shadow-md border p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Server Information</h2>
          <dl className="space-y-3">
            <div>
              <dt className="text-sm text-gray-500">Slug</dt>
              <dd className="text-sm font-medium text-gray-900">/{server.slug}</dd>
            </div>
            <div>
              <dt className="text-sm text-gray-500">Rate Limit</dt>
              <dd className="text-sm font-medium text-gray-900">
                {server.rate_limit === 0 ? 'Unlimited' : `${server.rate_limit} requests/min`}
              </dd>
            </div>
            <div>
              <dt className="text-sm text-gray-500">Created</dt>
              <dd className="text-sm font-medium text-gray-900">
                {server.create_date ? new Date(server.create_date).toLocaleString() : 'N/A'}
              </dd>
            </div>
            <div>
              <dt className="text-sm text-gray-500">Last Updated</dt>
              <dd className="text-sm font-medium text-gray-900">
                {server.update_date ? new Date(server.update_date).toLocaleString() : 'N/A'}
              </dd>
            </div>
          </dl>
        </div>

        {/* Agents Card */}
        <div className="bg-white rounded-lg shadow-md border p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Exposed Agents ({server.agents?.length || 0})</h2>

          {/* Warning for unavailable agents */}
          {server.agents && server.agents.some(a => !a.is_available) && (
            <div className="mb-4 bg-amber-50 border border-amber-200 rounded-lg p-3">
              <div className="flex items-start">
                <span className="text-amber-500 mr-2">!</span>
                <div className="text-sm text-amber-800">
                  <strong>Warning:</strong> Some agents are unavailable and won't be exposed as tools.
                  They may have been deleted or unmarked as tools.
                </div>
              </div>
            </div>
          )}

          {server.agents && server.agents.length > 0 ? (
            <ul className="space-y-2">
              {server.agents.map(agent => (
                <li
                  key={agent.agent_id}
                  className={`flex items-start p-2 rounded ${
                    agent.is_available ? 'bg-gray-50' : 'bg-red-50 border border-red-200'
                  }`}
                >
                  <span className={`mr-2 ${agent.is_available ? 'text-purple-500' : 'text-red-400'}`}>
                    {agent.is_available ? 'o' : '!'}
                  </span>
                  <div className="flex-1">
                    <div className={`text-sm font-medium ${agent.is_available ? 'text-gray-900' : 'text-red-700'}`}>
                      {agent.tool_name_override || agent.agent_name}
                      {!agent.is_available && (
                        <span className="ml-2 px-2 py-0.5 text-xs bg-red-100 text-red-700 rounded-full">
                          Unavailable
                        </span>
                      )}
                    </div>
                    {agent.agent_description && (
                      <div className="text-xs text-gray-500">{agent.agent_description}</div>
                    )}
                    {!agent.is_available && agent.unavailable_reason && (
                      <div className="text-xs text-red-600 mt-1">
                        Reason: {agent.unavailable_reason}
                      </div>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-gray-500">No agents exposed yet.</p>
          )}
        </div>
      </div>

      {/* Endpoint URLs */}
      <div className="bg-white rounded-lg shadow-md border p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Endpoint URLs</h2>

        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Primary Endpoint (slug-based)
            </label>
            <div className="flex items-center space-x-2">
              <code className="flex-1 p-3 bg-gray-100 rounded-lg text-sm font-mono break-all">
                {server.endpoint_url}
              </code>
              <button
                onClick={() => copyToClipboard(server.endpoint_url, 'endpoint')}
                className="px-3 py-2 text-sm bg-gray-200 hover:bg-gray-300 rounded-lg"
              >
                {copiedField === 'endpoint' ? 'Copied!' : 'Copy'}
              </button>
            </div>
          </div>

          {server.endpoint_url_by_id && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Fallback Endpoint (ID-based)
              </label>
              <div className="flex items-center space-x-2">
                <code className="flex-1 p-3 bg-gray-100 rounded-lg text-sm font-mono break-all">
                  {server.endpoint_url_by_id}
                </code>
                <button
                  onClick={() => copyToClipboard(server.endpoint_url_by_id!, 'endpoint_id')}
                  className="px-3 py-2 text-sm bg-gray-200 hover:bg-gray-300 rounded-lg"
                >
                  {copiedField === 'endpoint_id' ? 'Copied!' : 'Copy'}
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Connection Hints */}
      {server.connection_hints && (
        <div className="bg-white rounded-lg shadow-md border p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Connection Configuration</h2>

          {/* Claude Desktop */}
          <div className="mb-6">
            <h3 className="text-md font-medium text-gray-800 mb-2">Claude Desktop</h3>
            <p className="text-sm text-gray-600 mb-2">
              Add this configuration to your Claude Desktop settings file
              (<code className="text-xs bg-gray-100 px-1 rounded">claude_desktop_config.json</code>):
            </p>
            <div className="relative">
              <pre className="p-4 bg-gray-900 text-green-400 rounded-lg text-sm overflow-x-auto">
                {JSON.stringify(server.connection_hints.claude_desktop, null, 2)}
              </pre>
              <button
                onClick={() => copyToClipboard(JSON.stringify(server.connection_hints!.claude_desktop, null, 2), 'claude')}
                className="absolute top-2 right-2 px-2 py-1 text-xs bg-gray-700 hover:bg-gray-600 text-white rounded"
              >
                {copiedField === 'claude' ? 'Copied!' : 'Copy'}
              </button>
            </div>
          </div>

          {/* Cursor */}
          <div className="mb-6">
            <h3 className="text-md font-medium text-gray-800 mb-2">Cursor</h3>
            <p className="text-sm text-gray-600 mb-2">
              Add this to your Cursor MCP settings:
            </p>
            <div className="relative">
              <pre className="p-4 bg-gray-900 text-green-400 rounded-lg text-sm overflow-x-auto">
                {JSON.stringify(server.connection_hints.cursor, null, 2)}
              </pre>
              <button
                onClick={() => copyToClipboard(JSON.stringify(server.connection_hints!.cursor, null, 2), 'cursor')}
                className="absolute top-2 right-2 px-2 py-1 text-xs bg-gray-700 hover:bg-gray-600 text-white rounded"
              >
                {copiedField === 'cursor' ? 'Copied!' : 'Copy'}
              </button>
            </div>
          </div>

          {/* Curl Example */}
          <div>
            <h3 className="text-md font-medium text-gray-800 mb-2">Test with curl</h3>
            <p className="text-sm text-gray-600 mb-2">
              Test the MCP endpoint using curl:
            </p>
            <div className="relative">
              <pre className="p-4 bg-gray-900 text-green-400 rounded-lg text-sm overflow-x-auto whitespace-pre-wrap">
                {server.connection_hints.curl_example}
              </pre>
              <button
                onClick={() => copyToClipboard(server.connection_hints!.curl_example, 'curl')}
                className="absolute top-2 right-2 px-2 py-1 text-xs bg-gray-700 hover:bg-gray-600 text-white rounded"
              >
                {copiedField === 'curl' ? 'Copied!' : 'Copy'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Authentication Note */}
      <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
        <div className="flex">
          <span className="text-blue-400 text-xl mr-3">(i)</span>
          <div>
            <h3 className="text-sm font-medium text-blue-800">Authentication Required</h3>
            <p className="text-sm text-blue-600 mt-1">
              MCP endpoints require authentication. Use an API key from your app's API Keys settings
              and include it in the <code className="bg-blue-100 px-1 rounded">X-API-KEY</code> header.
            </p>
            <Link
              to={`/apps/${appId}/settings/api-keys`}
              className="mt-2 text-sm text-blue-800 hover:text-blue-900 underline inline-block"
            >
              Manage API Keys
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}

export default MCPServerDetailPage;
