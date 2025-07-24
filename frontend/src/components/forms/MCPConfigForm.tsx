import { useState, useEffect } from 'react';

interface MCPConfigFormData {
  name: string;
  server_name: string;
  description: string;
  transport_type: string;
  command: string;
  args: string;
  env: string;
}

interface MCPConfig {
  config_id: number;
  name: string;
  server_name: string;
  description: string;
  transport_type: string;
  command: string;
  args: string;
  env: string;
  created_at: string;
  available_transport_types: Array<{value: string, name: string}>;
}

interface MCPConfigFormProps {
  mcpConfig?: MCPConfig | null;
  onSubmit: (data: MCPConfigFormData) => Promise<void>;
  onCancel: () => void;
  loading?: boolean;
}

function MCPConfigForm({ mcpConfig, onSubmit, onCancel, loading = false }: MCPConfigFormProps) {
  const [formData, setFormData] = useState<MCPConfigFormData>({
    name: '',
    server_name: '',
    description: '',
    transport_type: '',
    command: '',
    args: '',
    env: ''
  });
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isEditing = !!mcpConfig && mcpConfig.config_id !== 0;

  // Available transport types (based on backend enum)
  const transportTypes = [
    { value: 'stdio', name: 'STDIO (Standard Input/Output)' },
    { value: 'sse', name: 'SSE (Server-Sent Events)' }
  ];

  // Transport-specific configurations and examples
  const getTransportHelp = (transportType: string) => {
    const help: Record<string, {description: string, commandExample: string, argsExample: string, envExample: string}> = {
      'stdio': {
        description: 'Communicates with the MCP server via standard input/output streams. Best for local processes.',
        commandExample: 'npx @modelcontextprotocol/server-filesystem',
        argsExample: '["/path/to/allowed/directory"]',
        envExample: '{"DEBUG": "true", "NODE_ENV": "production"}'
      },
      'sse': {
        description: 'Connects to MCP server via Server-Sent Events over HTTP. Best for remote services.',
        commandExample: 'https://your-mcp-server.com/mcp',
        argsExample: '[]',
        envExample: '{"API_KEY": "your-api-key"}'
      }
    };
    return help[transportType] || { description: '', commandExample: '', argsExample: '', envExample: '' };
  };

  // Initialize form with existing config data
  useEffect(() => {
    if (mcpConfig) {
      setFormData({
        name: mcpConfig.name || '',
        server_name: mcpConfig.server_name || '',
        description: mcpConfig.description || '',
        transport_type: mcpConfig.transport_type || '',
        command: mcpConfig.command || '',
        args: mcpConfig.args || '',
        env: mcpConfig.env || ''
      });
    }
  }, [mcpConfig]);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => {
    const { name, value } = e.target;
    setFormData(prev => ({
      ...prev,
      [name]: value
    }));
  };

  const validateJSON = (jsonString: string, fieldName: string): boolean => {
    if (!jsonString.trim()) return true; // Empty is valid
    try {
      JSON.parse(jsonString);
      return true;
    } catch {
      setError(`Invalid JSON format in ${fieldName}`);
      return false;
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    // Basic validation
    if (!formData.name.trim()) {
      setError('Config name is required');
      return;
    }
    if (!formData.server_name.trim()) {
      setError('Server name is required');
      return;
    }
    if (!formData.transport_type) {
      setError('Transport type is required');
      return;
    }
    if (!formData.command.trim()) {
      setError('Command/URL is required');
      return;
    }

    // Validate JSON fields
    if (!validateJSON(formData.args, 'Arguments')) return;
    if (!validateJSON(formData.env, 'Environment Variables')) return;

    try {
      setIsSubmitting(true);
      setError(null);
      await onSubmit(formData);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save MCP config');
    } finally {
      setIsSubmitting(false);
    }
  };

  const transportHelp = getTransportHelp(formData.transport_type);

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-3">
          <p className="text-red-600 text-sm">{error}</p>
        </div>
      )}

      {/* Config Name */}
      <div>
        <label htmlFor="name" className="block text-sm font-medium text-gray-700 mb-2">
          Configuration Name *
        </label>
        <input
          type="text"
          id="name"
          name="name"
          value={formData.name}
          onChange={handleChange}
          className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent"
          placeholder="e.g., Filesystem Server, GitHub MCP"
          required
        />
      </div>

      {/* Server Name */}
      <div>
        <label htmlFor="server_name" className="block text-sm font-medium text-gray-700 mb-2">
          Server Name *
        </label>
        <input
          type="text"
          id="server_name"
          name="server_name"
          value={formData.server_name}
          onChange={handleChange}
          className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent"
          placeholder="e.g., filesystem, github, database"
          required
        />
        <p className="mt-1 text-xs text-gray-500">
          Unique identifier for this MCP server configuration
        </p>
      </div>

      {/* Description */}
      <div>
        <label htmlFor="description" className="block text-sm font-medium text-gray-700 mb-2">
          Description
        </label>
        <textarea
          id="description"
          name="description"
          value={formData.description}
          onChange={handleChange}
          rows={2}
          className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent"
          placeholder="Optional description of this MCP configuration"
        />
      </div>

      {/* Transport Type */}
      <div>
        <label htmlFor="transport_type" className="block text-sm font-medium text-gray-700 mb-2">
          Transport Type *
        </label>
        <select
          id="transport_type"
          name="transport_type"
          value={formData.transport_type}
          onChange={handleChange}
          className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent"
          required
        >
          <option value="">Select transport type</option>
          {transportTypes.map((type) => (
            <option key={type.value} value={type.value}>
              {type.name}
            </option>
          ))}
        </select>
      </div>

      {/* Transport-specific help */}
      {formData.transport_type && (
        <div className="bg-purple-50 border border-purple-200 rounded-lg p-3">
          <h4 className="text-sm font-medium text-purple-800 mb-1">
            {transportTypes.find(t => t.value === formData.transport_type)?.name} Configuration
          </h4>
          <p className="text-xs text-purple-700">{transportHelp.description}</p>
        </div>
      )}

      {/* Command/URL */}
      <div>
        <label htmlFor="command" className="block text-sm font-medium text-gray-700 mb-2">
          {formData.transport_type === 'sse' ? 'Server URL *' : 'Command *'}
        </label>
        <input
          type="text"
          id="command"
          name="command"
          value={formData.command}
          onChange={handleChange}
          className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent"
          placeholder={transportHelp.commandExample}
          required
        />
        {formData.transport_type && (
          <p className="mt-1 text-xs text-gray-500">
            Example: {transportHelp.commandExample}
          </p>
        )}
      </div>

      {/* Arguments */}
      <div>
        <label htmlFor="args" className="block text-sm font-medium text-gray-700 mb-2">
          Arguments (JSON Array)
        </label>
        <textarea
          id="args"
          name="args"
          value={formData.args}
          onChange={handleChange}
          rows={3}
          className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent"
          placeholder={transportHelp.argsExample}
        />
        <p className="mt-1 text-xs text-gray-500">
          JSON array format. {formData.transport_type && `Example: ${transportHelp.argsExample}`}
        </p>
      </div>

      {/* Environment Variables */}
      <div>
        <label htmlFor="env" className="block text-sm font-medium text-gray-700 mb-2">
          Environment Variables (JSON Object)
        </label>
        <textarea
          id="env"
          name="env"
          value={formData.env}
          onChange={handleChange}
          rows={3}
          className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent"
          placeholder={transportHelp.envExample}
        />
        <p className="mt-1 text-xs text-gray-500">
          JSON object format. {formData.transport_type && `Example: ${transportHelp.envExample}`}
        </p>
      </div>

      {/* MCP Info Box */}
      <div className="bg-blue-50 border border-blue-200 rounded-lg p-3">
        <div className="flex">
          <div className="flex-shrink-0">
            <span className="text-blue-400 text-xl">🔌</span>
          </div>
          <div className="ml-3">
            <h3 className="text-sm font-medium text-blue-800">
              About Model Context Protocol (MCP)
            </h3>
            <div className="mt-2 text-xs text-blue-700">
              <p>
                MCP enables AI agents to connect to external tools and data sources securely. 
                Common servers include filesystem access, database connections, API integrations, 
                and custom business logic.
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Form Actions */}
      <div className="flex items-center justify-end space-x-3 pt-4 border-t border-gray-200">
        <button
          type="button"
          onClick={onCancel}
          className="px-4 py-2 text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors"
          disabled={isSubmitting}
        >
          Cancel
        </button>
        <button
          type="submit"
          disabled={isSubmitting}
          className="px-6 py-2 bg-purple-600 hover:bg-purple-700 disabled:bg-purple-400 text-white rounded-lg flex items-center transition-colors"
        >
          {isSubmitting && (
            <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
          )}
          {isSubmitting ? 'Saving...' : (isEditing ? 'Update Config' : 'Create Config')}
        </button>
      </div>
    </form>
  );
}

export default MCPConfigForm; 