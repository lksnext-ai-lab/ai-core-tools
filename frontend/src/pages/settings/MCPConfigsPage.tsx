import { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import Modal from '../../components/ui/Modal';
import MCPConfigForm from '../../components/forms/MCPConfigForm';
import { apiService } from '../../services/api';
import ActionDropdown from '../../components/ui/ActionDropdown';
import { useSettingsCache } from '../../contexts/SettingsCacheContext';
import { useAppRole } from '../../hooks/useAppRole';
import ReadOnlyBanner from '../../components/ui/ReadOnlyBanner';
import type { MCPConfig } from '../../core/types';
import Alert from '../../components/ui/Alert';

function MCPConfigsPage() {
  const { appId } = useParams();
  const settingsCache = useSettingsCache();
  const { isOwner, isAdmin, userRole } = useAppRole(appId);
  const [configs, setConfigs] = useState<MCPConfig[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingConfig, setEditingConfig] = useState<any>(null);

  // Load MCP configs from cache or API
  useEffect(() => {
    loadMCPConfigs();
  }, [appId]);

  async function loadMCPConfigs() {
    if (!appId) return;
    
    // Check if we have cached data first
    const cachedData = settingsCache.getMCPConfigs(appId);
    if (cachedData) {
      setConfigs(cachedData);
      setLoading(false);
      return;
    }
    
    // If no cache, load from API
    try {
      setLoading(true);
      setError(null);
      const response = await apiService.getMCPConfigs(parseInt(appId));
      setConfigs(response);
      // Cache the response
      settingsCache.setMCPConfigs(appId, response);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load MCP configs');
      console.error('Error loading MCP configs:', err);
    } finally {
      setLoading(false);
    }
  }

  async function forceReloadMCPConfigs() {
    if (!appId) return;
    
    try {
      setLoading(true);
      setError(null);
      const response = await apiService.getMCPConfigs(parseInt(appId));
      setConfigs(response);
      // Cache the response
      settingsCache.setMCPConfigs(appId, response);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load MCP configs');
      console.error('Error loading MCP configs:', err);
    } finally {
      setLoading(false);
    }
  }

  async function handleDelete(configId: number) {
    if (!confirm('Are you sure you want to delete this MCP config?')) {
      return;
    }

    if (!appId) return;

    try {
      await apiService.deleteMCPConfig(parseInt(appId), configId);
      // Remove from local state
      const newConfigs = configs.filter(c => c.config_id !== configId);
      setConfigs(newConfigs);
      // Update cache
      settingsCache.setMCPConfigs(appId, newConfigs);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete config');
      console.error('Error deleting MCP config:', err);
    }
  }

  function handleCreateConfig() {
    setEditingConfig(null);
    setIsModalOpen(true);
  }

  async function handleEditConfig(configId: number) {
    if (!appId) return;
    
    try {
      const config = await apiService.getMCPConfig(parseInt(appId), configId);
      setEditingConfig(config);
      setIsModalOpen(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load config details');
      console.error('Error loading MCP config:', err);
    }
  }

  async function handleSaveConfig(data: any) {
    if (!appId) return;

    try {
      if (editingConfig && editingConfig.config_id !== 0) {
        // Update existing config - no need to invalidate cache
        await apiService.updateMCPConfig(parseInt(appId), editingConfig.config_id, data);
        await loadMCPConfigs();
      } else {
        // Create new config - invalidate cache and force reload
        await apiService.createMCPConfig(parseInt(appId), data);
        settingsCache.invalidateMCPConfigs(appId);
        await forceReloadMCPConfigs();
      }
      
      setIsModalOpen(false);
      setEditingConfig(null);
    } catch (err) {
      throw new Error(err instanceof Error ? err.message : 'Failed to save config');
    }
  }

  function handleCloseModal() {
    setIsModalOpen(false);
    setEditingConfig(null);
  }

  if (loading) {
    return (
      
        <div className="p-6 text-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-purple-600 mx-auto"></div>
          <p className="mt-2 text-gray-600">Loading MCP configs...</p>
        </div>
      
    );
  }

  if (error) {
    return (
      <div className="p-6">
        <Alert type="error" message={error} onDismiss={() => loadMCPConfigs()} />
      </div>
    );
  }

  return (
    
      <div className="p-6">
        {/* Header */}
        <div className="flex justify-between items-center mb-6">
          <div>
            <h2 className="text-xl font-semibold text-gray-900">MCP Configs</h2>
            <p className="text-gray-600">Manage Model Context Protocol server configurations</p>
          </div>
          {isAdmin && (
            <button 
              onClick={handleCreateConfig}
              className="bg-purple-600 hover:bg-purple-700 text-white px-4 py-2 rounded-lg flex items-center"
            >
              <span className="mr-2">+</span>
              Add MCP Config
            </button>
          )}
        </div>
        
        {/* Read-only banner for non-admins */}
        {!isAdmin && <ReadOnlyBanner userRole={userRole} />}

        {/* Configs Table */}
        {configs.length > 0 ? (
          <div className="bg-white shadow rounded-lg overflow-visible">
            <div className="overflow-x-auto overflow-visible">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Name
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Description
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Created
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Actions
                    </th>
                  </tr>
                </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {configs.map((config) => (
                  <tr key={config.config_id} className="hover:bg-gray-50">
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div className="flex items-center">
                        <span className="text-purple-400 text-xl mr-3">🔌</span>
                        <div 
                          className="text-sm font-medium text-gray-900 cursor-pointer hover:text-blue-600 transition-colors"
                          onClick={() => handleEditConfig(config.config_id)}
                          >
                            {config.name}
                          </div>
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      <div className="text-sm text-gray-600 max-w-xs truncate">
                        {config.description || <span className="text-gray-400 italic">No description</span>}
                      </div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                      {config.created_at ? new Date(config.created_at).toLocaleDateString() : 'N/A'}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm font-medium relative">
                      {isAdmin ? (
                        <ActionDropdown
                          actions={[
                            {
                              label: 'Edit',
                              onClick: () => handleEditConfig(config.config_id),
                              icon: '✏️',
                              variant: 'primary'
                            },
                            {
                              label: 'Delete',
                              onClick: () => handleDelete(config.config_id),
                              icon: '🗑️',
                              variant: 'danger'
                            }
                          ]}
                          size="sm"
                        />
                      ) : (
                        <span className="text-gray-400 text-sm">View only</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            </div>
          </div>
        ) : (
          <div className="text-center py-12">
            <div className="text-6xl mb-4">🔌</div>
            <h3 className="text-lg font-semibold text-gray-900 mb-2">No MCP Configs</h3>
            <p className="text-gray-600 mb-6">
              Add your first MCP configuration to connect agents with external tools and data sources.
            </p>
            {isAdmin && (
              <button 
                onClick={handleCreateConfig}
                className="bg-purple-600 hover:bg-purple-700 text-white px-6 py-3 rounded-lg"
              >
                Add First MCP Config
              </button>
            )}
          </div>
        )}

        {/* Info Box */}
        <div className="mt-6 bg-purple-50 border border-purple-200 rounded-lg p-4">
          <div className="flex">
            <div className="flex-shrink-0">
              <span className="text-purple-400 text-xl">💡</span>
            </div>
            <div className="ml-3">
              <h3 className="text-sm font-medium text-purple-800">
                About Model Context Protocol (MCP)
              </h3>
              <div className="mt-2 text-sm text-purple-700">
                <p>
                  MCP enables secure, controlled connections between AI agents and external tools. 
                  Configure filesystem access, database connections, APIs, web browsers, and custom tools. 
                  Use STDIO for local processes or SSE for remote services.
                </p>
                <div className="mt-2">
                  <strong>Popular MCP Servers:</strong>
                  <ul className="list-disc list-inside mt-1 space-y-1">
                    <li><code>@modelcontextprotocol/server-filesystem</code> - File system access</li>
                    <li><code>@modelcontextprotocol/server-sqlite</code> - SQLite database queries</li>
                    <li><code>@modelcontextprotocol/server-github</code> - GitHub API integration</li>
                    <li><code>@modelcontextprotocol/server-brave-search</code> - Web search</li>
                  </ul>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Create/Edit Modal */}
        <Modal
          isOpen={isModalOpen}
          onClose={handleCloseModal}
          title={editingConfig ? 'Edit MCP Config' : 'Create New MCP Config'}
        >
          <MCPConfigForm
            mcpConfig={editingConfig}
            onSubmit={handleSaveConfig}
            onCancel={handleCloseModal}
          />
        </Modal>
      </div>
    
  );
}

export default MCPConfigsPage; 