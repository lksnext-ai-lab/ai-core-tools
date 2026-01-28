import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { apiService } from '../services/api';
import type { MCPServer, ToolAgent } from '../core/types';

function MCPServerFormPage() {
  const { appId, serverId } = useParams();
  const navigate = useNavigate();

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [toolAgents, setToolAgents] = useState<ToolAgent[]>([]);

  // Form state
  const [formData, setFormData] = useState({
    name: '',
    slug: '',
    description: '',
    is_active: true,
    rate_limit: 0,
    agent_ids: [] as number[],
  });

  const isEditing = serverId !== undefined && serverId !== 'new';

  useEffect(() => {
    if (!appId) {
      setLoading(false);
      return;
    }

    void loadData();
  }, [appId, serverId, isEditing]);

  async function loadData() {
    if (!appId) return;

    try {
      setLoading(true);
      setError(null);

      // Load available tool agents
      const agents = await apiService.getMCPServerToolAgents(parseInt(appId));
      setToolAgents(agents);

      // Load existing server if editing
      if (isEditing && serverId) {
        const server: MCPServer = await apiService.getMCPServer(parseInt(appId), parseInt(serverId));
        setFormData({
          name: server.name || '',
          slug: server.slug || '',
          description: server.description || '',
          is_active: server.is_active ?? true,
          rate_limit: server.rate_limit || 0,
          agent_ids: server.agents?.map(a => a.agent_id) || [],
        });
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load data');
      console.error('Error loading data:', err);
    } finally {
      setLoading(false);
    }
  }

  function handleInputChange(e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) {
    const { name, value, type } = e.target;
    const checked = (e.target as HTMLInputElement).checked;

    setFormData(prev => ({
      ...prev,
      [name]: type === 'checkbox' ? checked : type === 'number' ? parseInt(value) || 0 : value,
    }));
  }

  function handleAgentToggle(agentId: number) {
    setFormData(prev => ({
      ...prev,
      agent_ids: prev.agent_ids.includes(agentId)
        ? prev.agent_ids.filter(id => id !== agentId)
        : [...prev.agent_ids, agentId],
    }));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!appId) return;

    try {
      setSaving(true);
      setError(null);

      if (isEditing && serverId) {
        await apiService.updateMCPServer(parseInt(appId), parseInt(serverId), formData);
      } else {
        await apiService.createMCPServer(parseInt(appId), formData);
      }

      navigate(`/apps/${appId}/mcp-servers`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save MCP server');
      console.error('Error saving MCP server:', err);
    } finally {
      setSaving(false);
    }
  }

  function handleCancel() {
    navigate(`/apps/${appId}/mcp-servers`);
  }

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">
              {isEditing ? 'Edit MCP Server' : 'Create MCP Server'}
            </h1>
            <p className="text-gray-600">Configure your MCP server settings</p>
          </div>
        </div>

        <div className="flex items-center justify-center py-12">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-yellow-600"></div>
          <span className="ml-2">Loading...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">
            {isEditing ? 'Edit MCP Server' : 'Create MCP Server'}
          </h1>
          <p className="text-gray-600">Configure your MCP server to expose agents as tools</p>
        </div>
        <button
          onClick={handleCancel}
          className="px-4 py-2 text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-lg"
        >
          Back
        </button>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4">
          <div className="flex">
            <span className="text-red-400 text-xl mr-3">!</span>
            <div>
              <h3 className="text-sm font-medium text-red-800">Error</h3>
              <p className="text-sm text-red-600 mt-1">{error}</p>
            </div>
          </div>
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-6">
        {/* Basic Information */}
        <div className="bg-white rounded-lg shadow-md border p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Basic Information</h2>

          <div className="space-y-4">
            <div>
              <label htmlFor="name" className="block text-sm font-medium text-gray-700 mb-1">
                Name *
              </label>
              <input
                type="text"
                id="name"
                name="name"
                value={formData.name}
                onChange={handleInputChange}
                required
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-yellow-500 focus:border-transparent"
                placeholder="My MCP Server"
              />
            </div>

            <div>
              <label htmlFor="slug" className="block text-sm font-medium text-gray-700 mb-1">
                URL Slug
              </label>
              <div className="flex items-center">
                <span className="text-gray-500 text-sm mr-2">/mcp/v1/app-slug/</span>
                <input
                  type="text"
                  id="slug"
                  name="slug"
                  value={formData.slug}
                  onChange={handleInputChange}
                  className="flex-1 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-yellow-500 focus:border-transparent"
                  placeholder="my-server (auto-generated if empty)"
                  pattern="[a-z0-9-]+"
                />
              </div>
              <p className="text-xs text-gray-500 mt-1">
                URL-safe identifier. Use lowercase letters, numbers, and hyphens only.
              </p>
            </div>

            <div>
              <label htmlFor="description" className="block text-sm font-medium text-gray-700 mb-1">
                Description
              </label>
              <textarea
                id="description"
                name="description"
                value={formData.description}
                onChange={handleInputChange}
                rows={3}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-yellow-500 focus:border-transparent"
                placeholder="Describe what this MCP server does..."
              />
            </div>

            <div className="flex items-center space-x-4">
              <div className="flex items-center">
                <input
                  type="checkbox"
                  id="is_active"
                  name="is_active"
                  checked={formData.is_active}
                  onChange={handleInputChange}
                  className="h-4 w-4 text-yellow-600 focus:ring-yellow-500 border-gray-300 rounded"
                />
                <label htmlFor="is_active" className="ml-2 text-sm text-gray-700">
                  Active (server accepts requests)
                </label>
              </div>
            </div>

            <div>
              <label htmlFor="rate_limit" className="block text-sm font-medium text-gray-700 mb-1">
                Rate Limit (requests per minute)
              </label>
              <input
                type="number"
                id="rate_limit"
                name="rate_limit"
                value={formData.rate_limit}
                onChange={handleInputChange}
                min={0}
                className="w-32 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-yellow-500 focus:border-transparent"
              />
              <p className="text-xs text-gray-500 mt-1">
                0 = unlimited
              </p>
            </div>
          </div>
        </div>

        {/* Agent Selection */}
        <div className="bg-white rounded-lg shadow-md border p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Select Agents to Expose</h2>
          <p className="text-sm text-gray-600 mb-4">
            Choose which agents (marked as tools) to expose through this MCP server.
            These agents will be available as MCP tools for external clients.
          </p>

          {toolAgents.length === 0 ? (
            <div className="text-center py-8 bg-gray-50 rounded-lg">
              <div className="text-4xl mb-2">o</div>
              <p className="text-gray-600">No agents marked as tools available.</p>
              <p className="text-sm text-gray-500 mt-1">
                Create an agent and enable "Use as Tool" to expose it via MCP.
              </p>
            </div>
          ) : (
            <div className="space-y-2 max-h-64 overflow-y-auto">
              {toolAgents.map(agent => (
                <label
                  key={agent.agent_id}
                  className={`flex items-start p-3 rounded-lg border cursor-pointer transition-colors ${
                    formData.agent_ids.includes(agent.agent_id)
                      ? 'bg-purple-50 border-purple-300'
                      : 'bg-white border-gray-200 hover:bg-gray-50'
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={formData.agent_ids.includes(agent.agent_id)}
                    onChange={() => handleAgentToggle(agent.agent_id)}
                    className="h-4 w-4 text-purple-600 focus:ring-purple-500 border-gray-300 rounded mt-1"
                  />
                  <div className="ml-3">
                    <div className="text-sm font-medium text-gray-900">{agent.name}</div>
                    {agent.description && (
                      <div className="text-xs text-gray-500 mt-1">{agent.description}</div>
                    )}
                  </div>
                </label>
              ))}
            </div>
          )}

          <div className="mt-4 text-sm text-gray-500">
            {formData.agent_ids.length} agent{formData.agent_ids.length !== 1 ? 's' : ''} selected
          </div>
        </div>

        {/* Form Actions */}
        <div className="flex justify-end space-x-4">
          <button
            type="button"
            onClick={handleCancel}
            className="px-6 py-2 text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-lg"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={saving || !formData.name}
            className="px-6 py-2 text-white bg-yellow-600 hover:bg-yellow-700 rounded-lg disabled:opacity-50 disabled:cursor-not-allowed flex items-center"
          >
            {saving ? (
              <>
                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
                Saving...
              </>
            ) : (
              isEditing ? 'Update MCP Server' : 'Create MCP Server'
            )}
          </button>
        </div>
      </form>
    </div>
  );
}

export default MCPServerFormPage;
