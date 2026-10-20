import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { apiService } from '../services/api';
import { useApiMutation } from '../hooks/useApiMutation';
import { MESSAGES, errorMessage } from '../constants/messages';
import type { MCPServer, ToolAgent } from '../core/types';
import { LoadingState } from '../components/ui/LoadingState';
import { FormActions } from '../components/ui/FormActions';
import Alert from '../components/ui/Alert';
import Title from '../components/ui/Title';
import { FormCheckbox, FormField, FormTextArea } from '../components/ui/FormField';

function resolveInputValue(type: string, value: string, checked: boolean): string | number | boolean {
  if (type === 'checkbox') return checked;
  if (type === 'number') return Number.parseInt(value) || 0;
  return value;
}

function MCPServerFormPage() {
  const { appId, serverId } = useParams();
  const navigate = useNavigate();
  const mutate = useApiMutation();

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
      const agents = await apiService.getMCPServerToolAgents(Number.parseInt(appId));
      setToolAgents(agents);

      // Load existing server if editing
      if (isEditing && serverId) {
        const server: MCPServer = await apiService.getMCPServer(Number.parseInt(appId), Number.parseInt(serverId));
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
      [name]: resolveInputValue(type, value, checked),
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

    setError(null);
    setSaving(true);
    const result = await mutate(
      () =>
        isEditing && serverId
          ? apiService.updateMCPServer(Number.parseInt(appId), Number.parseInt(serverId), formData)
          : apiService.createMCPServer(Number.parseInt(appId), formData),
      {
        loading: isEditing ? MESSAGES.UPDATING('MCP server') : MESSAGES.CREATING('MCP server'),
        success: isEditing ? MESSAGES.UPDATED('MCP server') : MESSAGES.CREATED('MCP server'),
        error: (err) => errorMessage(err, MESSAGES.SAVE_FAILED('MCP server')),
      },
    );
    setSaving(false);

    if (result !== undefined) {
      navigate(`/apps/${appId}/mcp-servers`);
    }
  }

  function handleCancel() {
    navigate(`/apps/${appId}/mcp-servers`);
  }

  const submitLabel = isEditing ? 'Update MCP Server' : 'Create MCP Server';

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <Title variant="titPrincipal" titulo={isEditing ? 'Edit MCP Server' : 'Create MCP Server'} subtitulo="Configure your MCP server settings" ></Title>
        </div>

        <LoadingState variant="page" message="Loading..." />
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-4xl mx-auto">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <Title variant="titPrincipal" titulo={isEditing ? 'Edit MCP Server' : 'Create MCP Server'} subtitulo="Configure your MCP server settings" subtitleMarginBottom={20}></Title>
      </div>

      {error && <Alert type="error" message={error} />}

      <form onSubmit={handleSubmit} className="space-y-6">
        {/* Basic Information */}
        <div>
          <h2 className="text-[11px] font-semibold text-bronze dark:text-bronze-dark uppercase mb-4">Basic Information</h2>

          <div className="space-y-4">
            <FormField
              label="Name"
              id="name"
              value={formData.name}
              onChange={handleInputChange}
              required
              placeholder="My MCP Server"
            />

            <div>
              <label htmlFor="slug" className="block text-sm font-medium text-fg dark:text-fg-dark mb-1">
                URL Slug
              </label>
              <div className="flex items-center">
                <span className="bg-surface-hover dark:bg-surface-dark border border-line-strong dark:border-line-strong-dark rounded-l-lg border-r-0 px-3 py-2 text-fg-tertiary dark:text-fg-tertiary-dark text-sm">/mcp/v1/app-slug/</span>
                <FormField
                  label="URL Slug"
                  labelClassName="hidden"
                  id="slug"
                  value={formData.slug}
                  onChange={handleInputChange}
                  className="flex-1 min-w-0"
                  inputClassName="rounded-l-none"
                  placeholder="my-server (auto-generated if empty)"
                  pattern="[a-z0-9-]+"
                />
              </div>
              <p className="text-xs text-fg-tertiary dark:text-fg-tertiary-dark mt-1">
                URL-safe identifier. Use lowercase letters, numbers, and hyphens only.
              </p>
            </div>

            <FormTextArea
              label="Description"
              id="description"
              value={formData.description}
              onChange={handleInputChange}
              rows={3}
              placeholder="Describe what this MCP server does..."
            />

            <FormCheckbox
              label="Active (server accepts requests)"
              id="is_active"
              checked={formData.is_active}
              onChange={handleInputChange}
            />

            <FormField
              label="Rate Limit (requests per minute)"
              id="rate_limit"
              type="number"
              value={formData.rate_limit}
              onChange={handleInputChange}
              min={0}
              className="w-[250px]"
              helpText="0 = unlimited"
            />
          </div>
        </div>

        {/* Agent Selection */}
        <div className="border-t border-line-strong dark:border-line-strong-dark py-6">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h2 className="text-[11px] font-semibold text-bronze dark:text-bronze-dark uppercase mb-4">Select Agents to Expose</h2>
              <p className="text-sm text-fg-tertiary dark:text-fg-tertiary-dark mb-4">
                Choose which agents (marked as tools) to expose through this MCP server.
                These agents will be available as MCP tools for external clients.
              </p>
            </div>
            <span className="shrink-0 text-sm text-fg-tertiary dark:text-fg-tertiary-dark">
              {formData.agent_ids.length} agent{formData.agent_ids.length === 1 ? '' : 's'} selected
            </span>
          </div>

          {toolAgents.length === 0 ? (
            <div className="text-center py-8 bg-gray-50 rounded-lg">
              <div className="text-4xl mb-2">o</div>
              <p className="text-fg-secondary dark:text-fg-secondary-dark">No agents marked as tools available.</p>
              <p className="text-sm text-fg-secondary dark:text-fg-secondary-dark mt-1">
                Create an agent and enable "Use as Tool" to expose it via MCP.
              </p>
            </div>
          ) : (
            <div className="space-y-2 max-h-64 overflow-y-auto">
              {toolAgents.map((agent) => (
                <div
                  key={agent.agent_id}
                  onClick={(event) => {
                    const target = event.target;
                    if (target instanceof HTMLElement && target.closest('input, label')) return;
                    handleAgentToggle(agent.agent_id);
                  }}
                  className={`flex items-start p-3 rounded-lg border cursor-pointer transition-colors ${
                    formData.agent_ids.includes(agent.agent_id)
                      ? 'bg-surface-tint dark:bg-surface-tint-dark border border-fg dark:border-fg'
                      : 'border-in-line  hover:bg-tableCab dark:bg-btCard-dark'
                  }`}
                >
                  <FormCheckbox
                    label={agent.name}
                    id={`agent-${agent.agent_id}`}
                    checked={formData.agent_ids.includes(agent.agent_id)}
                    onChange={() => handleAgentToggle(agent.agent_id)}
                    helpText={agent.description}
                  />
                </div>
              ))}
            </div>
          )}

        </div>

        {/* Form Actions */}
        <FormActions
          onCancel={handleCancel}
          isSubmitting={saving}
          submitLabel={submitLabel}
          submitDisabled={!formData.name}
        />
      </form>
    </div>
  );
}

export default MCPServerFormPage;
