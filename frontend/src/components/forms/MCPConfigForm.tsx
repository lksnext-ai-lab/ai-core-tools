import { useState, useEffect } from 'react';
import FormActions from './FormActions';

interface MCPConfigFormData {
  name: string;
  description: string;
  config: string;
}

interface MCPConfig {
  config_id: number;
  name: string;
  description: string;
  config: string;
  created_at: string;
}

interface MCPConfigFormProps {
  mcpConfig?: MCPConfig | null;
  onSubmit: (data: MCPConfigFormData) => Promise<void>;
  onCancel: () => void;
}

function MCPConfigForm({ mcpConfig, onSubmit, onCancel }: Readonly<MCPConfigFormProps>) {
  const [formData, setFormData] = useState<MCPConfigFormData>({
    name: '',
    description: '',
    config: '{}'
  });
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isEditing = !!mcpConfig && mcpConfig.config_id !== 0;

  // Initialize form with existing config data
  useEffect(() => {
    if (mcpConfig) {
      setFormData({
        name: mcpConfig.name || '',
        description: mcpConfig.description || '',
        config: mcpConfig.config || '{}'
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

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    // Basic validation
    if (!formData.name.trim()) {
      setError('Config name is required');
      return;
    }
    
    if (!formData.config.trim()) {
      setError('Config is required');
      return;
    }

    // Validate JSON config
    try {
      JSON.parse(formData.config);
    } catch {
      setError('Invalid JSON format in config');
      return;
    }

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
          placeholder="e.g., Playwright MCP, Filesystem Server"
          required
        />
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

      {/* Config JSON */}
      <div>
        <label htmlFor="config" className="block text-sm font-medium text-gray-700 mb-2">
          MCP Server Configuration (JSON) *
        </label>
        <textarea
          id="config"
          name="config"
          value={formData.config}
          onChange={handleChange}
          rows={12}
          className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent font-mono text-sm"
          placeholder='{&#10;  "playwright": {&#10;    "command": "npx",&#10;    "args": ["@playwright/mcp@latest", "--isolated"]&#10;  }&#10;}'
          required
        />
        <p className="mt-2 text-xs text-gray-500">
          Full MCP server configuration in JSON format. This matches the structure used in your <code className="bg-gray-100 px-1 py-0.5 rounded">mcp.json</code> file.
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
            <div className="mt-2 text-xs text-blue-700 space-y-2">
              <p>
                MCP enables AI agents to connect to external tools and data sources securely.
              </p>
              <p className="font-mono bg-blue-100 p-2 rounded text-xs">
                Example stdio config:<br/>
                &#123;"server-name": &#123;"command": "npx", "args": ["package@latest"]&#125;&#125;
              </p>
              <p className="font-mono bg-blue-100 p-2 rounded text-xs">
                Example SSE config:<br/>
                &#123;"server-name": &#123;"url": "https://server.com", "transport": "sse"&#125;&#125;
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Form Actions */}
      <FormActions
        onCancel={onCancel}
        isSubmitting={isSubmitting}
        isEditing={isEditing}
        submitLabel={isEditing ? 'Update Config' : 'Create Config'}
        submitButtonColor="purple"
      />
    </form>
  );
}

export default MCPConfigForm; 