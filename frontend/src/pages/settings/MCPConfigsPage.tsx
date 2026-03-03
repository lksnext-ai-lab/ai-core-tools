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
import Table from '../../components/ui/Table';
import { AppRole } from '../../types/roles';
import ImportModal, { 
  type ConflictMode, 
  type ImportResponse 
} from '../../components/ui/ImportModal';

function MCPConfigsPage() {
  const { appId } = useParams();
  const settingsCache = useSettingsCache();
  const { hasMinRole, userRole } = useAppRole(appId);
  const canEdit = hasMinRole(AppRole.ADMINISTRATOR);
  const [configs, setConfigs] = useState<MCPConfig[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingConfig, setEditingConfig] = useState<any>(null);
  const [testResult, setTestResult] = useState<any>(null);
  const [isTestModalOpen, setIsTestModalOpen] = useState(false);
  const [testingConfigId, setTestingConfigId] = useState<number | null>(null);
  const [showImportModal, setShowImportModal] = useState(false);
  const [exportingConfigId, setExportingConfigId] = useState<number | null>(null);
  const [notification, setNotification] = useState<{
    message: string; 
    type: 'success' | 'error'
  } | null>(null);

  // Load MCP configs from cache or API
  useEffect(() => {
    loadMCPConfigs();
  }, [appId]);

  async function handleTestConnection(configId: number) {
    if (!appId) return;
    setTestingConfigId(configId);
    setTestResult(null);
    setIsTestModalOpen(true);
    
    try {
      const result = await apiService.testMCPConnection(parseInt(appId), configId);
      setTestResult(result);
    } catch (err) {
      setTestResult({
        status: 'error',
        message: err instanceof Error ? err.message : 'Failed to test connection'
      });
    } finally {
      setTestingConfigId(null);
    }
  }

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

  async function handleExport(configId: number) {
    if (!appId) return;
    setExportingConfigId(configId);
    
    try {
      const blob = await apiService.exportMCPConfig(
        parseInt(appId), 
        configId
      );
      
      // Find config name for filename
      const config = configs.find(c => c.config_id === configId);
      const configName = config?.name || 'mcp-config';
      const sanitizedName = configName.replace(/[^a-z0-9]/gi, '-').toLowerCase();
      const timestamp = new Date().toISOString().split('T')[0];
      const filename = `mcp-config-${sanitizedName}-${timestamp}.json`;
      
      // Create download link
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      a.remove();
      
      // Show security info about auth tokens
      setNotification({
        message: (
          'Configuration exported. Remember that authentication tokens ' +
          'must be reconfigured after import.'
        ),
        type: 'success'
      });
      setTimeout(() => setNotification(null), 7000);
    } catch (err) {
      setNotification({
        message: err instanceof Error ? err.message : 'Failed to export config',
        type: 'error'
      });
      setTimeout(() => setNotification(null), 5000);
    } finally {
      setExportingConfigId(null);
    }
  }

  async function handleImport(
    file: File,
    conflictMode: ConflictMode,
    newName?: string
  ): Promise<ImportResponse> {
    if (!appId) throw new Error('App ID not found');
    
    try {
      const result = await apiService.importMCPConfig(
        parseInt(appId),
        file,
        conflictMode,
        newName
      );
      
      if (result.success) {
        // Close modal immediately
        setShowImportModal(false);
        
        // Build message with warnings
        let message = result.message || 'Import completed successfully';
        if (result.summary?.warnings && result.summary.warnings.length > 0) {
          message += '. ' + result.summary.warnings.join('. ');
        }
        
        // Show success notification with warnings
        setNotification({
          message,
          type: 'success'
        });
        
        // Invalidate cache and refresh the list
        settingsCache.invalidateMCPConfigs(appId);
        await forceReloadMCPConfigs();
        
        // Auto-dismiss notification after 7 seconds
        setTimeout(() => setNotification(null), 7000);
      }
      
      return result;
    } catch (err) {
      // Show error notification
      setNotification({
        message: err instanceof Error ? err.message : 'Import failed',
        type: 'error'
      });
      setTimeout(() => setNotification(null), 5000);
      throw err;
    }
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
            <p className="text-gray-600">
              Manage Model Context Protocol server configurations
            </p>
          </div>
          {canEdit && (
            <div className="flex gap-2">
              <button
                onClick={() => setShowImportModal(true)}
                className={
                  "border border-gray-300 hover:bg-gray-50 text-gray-700 " +
                  "px-4 py-2 rounded-lg flex items-center"
                }
              >
                <span className="mr-2">📤</span>Import
              </button>
              <button 
                onClick={handleCreateConfig}
                className={
                  "bg-purple-600 hover:bg-purple-700 text-white " +
                  "px-4 py-2 rounded-lg flex items-center"
                }
              >
                <span className="mr-2">+</span>
                {' '}Add MCP Config
              </button>
            </div>
          )}
        </div>
        
        {/* Read-only banner for non-admins */}
        {!canEdit && (
          <ReadOnlyBanner 
            userRole={userRole} 
            minRole={AppRole.ADMINISTRATOR} 
          />
        )}

        {/* Security Alert */}
        {canEdit && (
          <Alert 
            type="warning" 
            title="Security Notice" 
            message={
              "MCP configurations export without authentication tokens for " +
              "security. You must reconfigure authentication tokens and API " +
              "keys after importing a configuration."
            } 
            className="mb-4" 
          />
        )}

        {/* Notification Banner */}
        {notification && (
          <div className={
            `mb-4 rounded-lg p-4 ${
              notification.type === 'success' 
                ? 'bg-green-50 border border-green-200' 
                : 'bg-red-50 border border-red-200'
            }`
          }>
            <div className="flex items-start">
              <div className="flex-shrink-0">
                <span className={
                  `text-xl ${
                    notification.type === 'success' 
                      ? 'text-green-400' 
                      : 'text-red-400'
                  }`
                }>
                  {notification.type === 'success' ? '✓' : '✗'}
                </span>
              </div>
              <div className="ml-3 flex-1">
                <p className={
                  `text-sm font-medium ${
                    notification.type === 'success' 
                      ? 'text-green-800' 
                      : 'text-red-800'
                  }`
                }>
                  {notification.message}
                </p>
              </div>
              <button
                onClick={() => setNotification(null)}
                className={
                  `ml-3 inline-flex rounded-md p-1.5 ${
                    notification.type === 'success' 
                      ? 'text-green-500 hover:bg-green-100' 
                      : 'text-red-500 hover:bg-red-100'
                  } focus:outline-none`
                }
              >
                <span className="sr-only">Dismiss</span>
                <span className="text-lg">×</span>
              </button>
            </div>
          </div>
        )}

        {/* Configs Table */}
        <Table
          data={configs}
          keyExtractor={(config) => config.config_id.toString()}
          columns={[
            {
              header: 'Name',
              render: (config) => (
                <div className="flex items-center">
                  <span className="text-purple-400 text-xl mr-3">🔌</span>
                  {canEdit ? (
                    <button
                      type="button"
                      className="text-sm font-medium text-gray-900 hover:text-blue-600 transition-colors text-left"
                      onClick={() => void handleEditConfig(config.config_id)}
                    >
                      {config.name}
                    </button>
                  ) : (
                    <span className="text-sm font-medium text-gray-900">
                      {config.name}
                    </span>
                  )}
                </div>
              )
            },
            {
              header: 'Description',
              render: (config) => (
                <div className="text-sm text-gray-600 max-w-xs truncate">
                  {config.description || <span className="text-gray-400 italic">No description</span>}
                </div>
              ),
              className: 'px-6 py-4'
            },
            {
              header: 'Created',
              render: (config) => config.created_at ? new Date(config.created_at).toLocaleDateString() : 'N/A',
              className: 'px-6 py-4 whitespace-nowrap text-sm text-gray-500'
            },
            {
              header: 'Actions',
              className: 'relative',
              render: (config) => (
                canEdit ? (
                  <ActionDropdown
                    actions={[
                      ...(canEdit ? [{
                        label: (
                          exportingConfigId === config.config_id 
                            ? 'Exporting...' 
                            : 'Export'
                        ),
                        onClick: () => { void handleExport(config.config_id); },
                        icon: (
                          exportingConfigId === config.config_id ? '⏳' : '📥'
                        ),
                        disabled: exportingConfigId === config.config_id
                      }] : []),
                      ...(canEdit ? [{
                        label: (
                          testingConfigId === config.config_id 
                            ? 'Testing...' 
                            : 'Test Connection'
                        ),
                        onClick: () => { 
                          void handleTestConnection(config.config_id); 
                        },
                        icon: (
                          testingConfigId === config.config_id ? '⏳' : '🔌'
                        ),
                        disabled: testingConfigId === config.config_id
                      }] : []),
                      {
                        label: 'Edit',
                        onClick: () => { 
                          void handleEditConfig(config.config_id); 
                        },
                        icon: '✏️',
                        variant: 'primary'
                      },
                      {
                        label: 'Delete',
                        onClick: () => { void handleDelete(config.config_id); },
                        icon: '🗑️',
                        variant: 'danger'
                      }
                    ]}
                    size="sm"
                  />
                ) : (
                  <span className="text-gray-400 text-sm">View only</span>
                )
              )
            }
          ]}
          emptyIcon="🔌"
          emptyMessage="No MCP Configs"
          emptySubMessage="Add your first MCP configuration to connect agents with external tools and data sources."
          loading={loading}
        />

        {!loading && configs.length === 0 && canEdit && (
          <div className="text-center py-6">
            <button 
              onClick={handleCreateConfig}
              className="bg-purple-600 hover:bg-purple-700 text-white px-6 py-3 rounded-lg"
            >
              Add First MCP Config
            </button>
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

        {/* Test Result Modal */}
        <Modal
          isOpen={isTestModalOpen}
          onClose={() => !testingConfigId && setIsTestModalOpen(false)}
          title="Connection Test Result"
        >
          <div className="p-4">
            {testingConfigId ? (
              <div className="text-center py-8">
                <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-purple-600 mx-auto mb-4"></div>
                <p className="text-gray-600">Testing connection to MCP server...</p>
              </div>
            ) : testResult && (
              <div>
                <div className={`mb-4 p-3 rounded ${testResult.status === 'success' ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'}`}>
                  <strong>Status:</strong> {testResult.status === 'success' ? 'Success' : 'Error'}
                  <br />
                  <strong>Message:</strong> {testResult.message}
                </div>
                
                {testResult.tools && testResult.tools.length > 0 && (
                  <div>
                    <h4 className="font-semibold mb-2">Available Tools:</h4>
                    <div className="max-h-60 overflow-y-auto border rounded">
                      <table className="min-w-full divide-y divide-gray-200">
                        <thead className="bg-gray-50">
                          <tr>
                            <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Name</th>
                            <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Description</th>
                          </tr>
                        </thead>
                        <tbody className="bg-white divide-y divide-gray-200">
                          {testResult.tools.map((tool: any, index: number) => (
                            <tr key={index}>
                              <td className="px-4 py-2 text-sm font-medium text-gray-900">{tool.name}</td>
                              <td className="px-4 py-2 text-sm text-gray-500">{tool.description}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </div>
            )}
            {!testingConfigId && (
              <div className="mt-4 flex justify-end">
                <button
                  onClick={() => setIsTestModalOpen(false)}
                  className="bg-gray-200 hover:bg-gray-300 text-gray-800 px-4 py-2 rounded"
                >
                  Close
                </button>
              </div>
            )}
          </div>
        </Modal>
        {/* Import Modal */}
        <ImportModal
          isOpen={showImportModal}
          onClose={() => setShowImportModal(false)}
          onImport={handleImport}
          componentType="mcp_config"
          componentLabel="MCP Configuration"
        />      </div>
    
  );
}

export default MCPConfigsPage; 