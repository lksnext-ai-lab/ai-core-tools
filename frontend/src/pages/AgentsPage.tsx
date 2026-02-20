import { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { apiService } from '../services/api';
import ActionDropdown from '../components/ui/ActionDropdown';
import Alert from '../components/ui/Alert';
import Table from '../components/ui/Table';
import { useAppRole } from '../hooks/useAppRole';
import { AppRole } from '../types/roles';
import ReadOnlyBanner from '../components/ui/ReadOnlyBanner';
import ImportModal, { type ConflictMode, type ImportResponse } from '../components/ui/ImportModal';
import type { AgentMCPUsage } from '../core/types';

// Define the Agent type
interface Agent {
  agent_id: number;
  name: string;
  type: string;
  is_tool: boolean;
  created_at: string;
  request_count: number;
  description?: string;
  service_id?: number;
  ai_service?: {
    name: string;
    model_name: string;
    provider: string;
  };
}

// Define the App type
interface App {
  app_id: number;
  name: string;
}

function AgentsPage() {
  const { appId } = useParams();
  const navigate = useNavigate();
  const { hasMinRole, userRole } = useAppRole(appId);
  const canEdit = hasMinRole(AppRole.EDITOR);
  
  const [agents, setAgents] = useState<Agent[]>([]);
  const [app, setApp] = useState<App | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [agentToDelete, setAgentToDelete] = useState<Agent | null>(null);
  const [deleteAgentMcpUsage, setDeleteAgentMcpUsage] = useState<AgentMCPUsage | null>(null);
  const [loadingMcpUsage, setLoadingMcpUsage] = useState(false);
  const [showImportModal, setShowImportModal] = useState(false);
  const [showExportDialog, setShowExportDialog] = useState(false);
  const [agentToExport, setAgentToExport] = useState<Agent | null>(null);
  const [exportOptions, setExportOptions] = useState({
    includeAIService: true,
    includeSilo: true,
    includeOutputParser: true,
    includeMCPConfigs: true,
    includeAgentTools: true,
  });
  const [notification, setNotification] = useState<{ message: string; type: 'success' | 'error' | 'warning' } | null>(null);
  const [requiresAIServiceSelection, setRequiresAIServiceSelection] = useState(false);
  const [availableAIServices, setAvailableAIServices] = useState<Array<{ id: number; name: string }>>([]);
  const [selectedAIServiceId, setSelectedAIServiceId] = useState<number | undefined>(undefined);

  useEffect(() => {
    loadData();
  }, [appId]);

  async function loadData() {
    if (!appId) return;
    
    try {
      setLoading(true);
      setError(null);
      
      const [agentsResponse, appResponse] = await Promise.all([
        apiService.getAgents(parseInt(appId)),
        apiService.getApp(parseInt(appId))
      ]);
      
      setAgents(agentsResponse);
      setApp(appResponse);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load data');
      console.error('Error loading data:', err);
    } finally {
      setLoading(false);
    }
  }

  const handleCreateAgent = () => {
    navigate(`/apps/${appId}/agents/0`);
  };

  const handleEditAgent = (agentId: number) => {
    navigate(`/apps/${appId}/agents/${agentId}`);
  };

  const handlePlayground = (agentId: number) => {
    navigate(`/apps/${appId}/agents/${agentId}/playground`);
  };

  const handleDeleteAgent = async (agent: Agent) => {
    if (!appId) return;

    setAgentToDelete(agent);
    setShowDeleteModal(true);
    setDeleteAgentMcpUsage(null);

    // Check if agent is used in MCP servers
    if (agent.is_tool) {
      try {
        setLoadingMcpUsage(true);
        const usage = await apiService.getAgentMCPUsage(parseInt(appId), agent.agent_id);
        setDeleteAgentMcpUsage(usage);
      } catch (err) {
        console.error('Error loading MCP usage:', err);
      } finally {
        setLoadingMcpUsage(false);
      }
    }
  };

  const confirmDeleteAgent = async () => {
    if (!agentToDelete || !appId) return;

    try {
      await apiService.deleteAgent(parseInt(appId), agentToDelete.agent_id);
      setAgents(agents.filter(a => a.agent_id !== agentToDelete.agent_id));
      setShowDeleteModal(false);
      setAgentToDelete(null);
      setDeleteAgentMcpUsage(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete agent');
      console.error('Error deleting agent:', err);
    }
  };

  const handleExportClick = (agent: Agent) => {
    setAgentToExport(agent);
    setShowExportDialog(true);
  };

  const handleExport = async () => {
    if (!agentToExport || !appId) return;

    try {
      const blob = await apiService.exportAgent(
        parseInt(appId),
        agentToExport.agent_id,
        exportOptions.includeAIService,
        exportOptions.includeSilo,
        exportOptions.includeOutputParser,
        exportOptions.includeMCPConfigs,
        exportOptions.includeAgentTools
      );
      
      // Generate filename
      const timestamp = new Date().toISOString().split('T')[0];
      const sanitizedName = agentToExport.name.replace(/[^a-z0-9]/gi, '_').toLowerCase();
      const filename = `agent-${sanitizedName}-${timestamp}.json`;
      
      // Download
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);

      setShowExportDialog(false);
      setAgentToExport(null);
      setNotification({
        message: 'Agent exported successfully. Note: Conversation history excluded.',
        type: 'warning'
      });
      setTimeout(() => setNotification(null), 7000);
    } catch (err) {
      setNotification({
        message: err instanceof Error ? err.message : 'Failed to export agent',
        type: 'error'
      });
      setTimeout(() => setNotification(null), 5000);
      console.error('Error exporting agent:', err);
    }
  };

  const handleImport = async (
    file: File,
    conflictMode: ConflictMode,
    newName?: string
  ): Promise<ImportResponse> => {
    if (!appId) {
      throw new Error('App ID is required');
    }

    try {
      // Parse file to check if AI service selection is needed
      if (!requiresAIServiceSelection) {
        const fileContent = await file.text();
        const fileData = JSON.parse(fileContent);
        
        // Check if AI service is needed but not bundled
        if (fileData.agent?.service_name && !fileData.ai_service) {
          // Fetch available AI services
          const services = await apiService.getAIServices(parseInt(appId));
          setAvailableAIServices(
            services.map((svc: any) => ({ id: svc.service_id, name: svc.name }))
          );
          setRequiresAIServiceSelection(true);
          
          return {
            success: false,
            message: 'Please select an AI service to continue',
          };
        }
      }

      // Perform import
      const result = await apiService.importAgent(
        parseInt(appId),
        file,
        conflictMode,
        newName,
        selectedAIServiceId
      );

      if (result.success) {
        setShowImportModal(false);
        setNotification({
          message: result.message || 'Agent imported successfully',
          type: 'success'
        });
        void loadData(); // Reload agents list
        setTimeout(() => setNotification(null), 5000);
        
        // Reset AI service selection state
        setRequiresAIServiceSelection(false);
        setSelectedAIServiceId(undefined);
      }

      return result;
    } catch (err: any) {
      return {
        success: false,
        message: err?.message || 'Import failed',
      };
    }
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString();
  };

  const getAgentTypeIcon = (type: string) => {
    switch (type) {
      case 'ocr_agent':
        return '📷';
      case 'agent':
      default:
        return '🤖';
    }
  };

  const getAgentTypeLabel = (type: string) => {
    switch (type) {
      case 'ocr_agent':
        return 'OCR Agent';
      case 'agent':
      default:
        return 'AI Agent';
    }
  };

  if (loading) {
    return (
      <div className="space-y-6">
        {/* Page Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Agents</h1>
            <p className="text-gray-600">Manage your AI agents for app {app?.name || appId}</p>
          </div>
        </div>

        <div className="flex items-center justify-center py-12">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
          <span className="ml-2">Loading agents...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Agents</h1>
          <p className="text-gray-600">Manage your AI agents for app {app?.name || appId}</p>
        </div>
        <div className="flex items-center space-x-3">
          {hasMinRole(AppRole.ADMINISTRATOR) && (
            <button
              onClick={() => setShowImportModal(true)}
              className="bg-green-600 hover:bg-green-700 text-white px-4 py-2 rounded-lg flex items-center"
            >
              <span aria-hidden="true" className="mr-2">⬆️</span>
              <span>Import Agent</span>
            </button>
          )}
          {canEdit && (
            <button 
              onClick={handleCreateAgent}
              className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg flex items-center"
            >
              <span className="mr-2">+</span>
              {' '}Create Agent
            </button>
          )}
        </div>
      </div>

      {!canEdit && <ReadOnlyBanner userRole={userRole} minRole={AppRole.EDITOR} />}

      {/* Error Message */}
      {error && <Alert type="error" message={error} onDismiss={() => setError(null)} />}

      {/* Notification */}
      {notification && (
        <Alert
          type={notification.type}
          message={notification.message}
          onDismiss={() => setNotification(null)}
        />
      )}

      <Table
        data={agents}
        keyExtractor={(agent) => agent.agent_id.toString()}
        columns={[
          {
            header: 'Agent',
            render: (agent) => (
              <div className="flex items-center">
                <div className="flex-shrink-0 h-10 w-10">
                  <div className="h-10 w-10 rounded-lg bg-blue-100 flex items-center justify-center">
                    <span className="text-blue-600 text-lg">{getAgentTypeIcon(agent.type)}</span>
                  </div>
                </div>
                <div className="ml-4">
                  <div className="text-sm font-medium text-gray-900">
                    {canEdit ? (
                      <Link 
                        to={`/apps/${appId}/agents/${agent.agent_id}`} 
                        className="text-sm font-medium text-gray-900 hover:text-blue-600 transition-colors"
                      >
                        {agent.name}
                      </Link>
                    ) : (
                      <span className="text-sm font-medium text-gray-900">
                        {agent.name}
                      </span>
                    )}
                  </div>
                  {agent.is_tool && (
                    <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-yellow-100 text-yellow-800">
                      Tool 
                    </span>
                  )}
                </div>
              </div>
            )
          },
          {
            header: 'Description',
            render: (agent) => (
              <div className="text-sm text-gray-900 max-w-xs">
                {agent.description ? (
                  <div className="truncate" title={agent.description}>
                    {agent.description}
                  </div>
                ) : (
                  <span className="text-gray-400 italic">No description</span>
                )}
              </div>
            ),
            className: 'px-6 py-4'
          },
          {
            header: 'Type',
            render: (agent) => (
              <span className="inline-flex px-2 py-1 text-xs font-semibold rounded-full bg-gray-100 text-gray-800">
                {getAgentTypeLabel(agent.type)}
              </span>
            )
          },
          {
            header: 'AI Service',
            render: (agent) => (
              agent.ai_service ? (
                <div className="text-sm">
                  <div className="font-medium text-gray-900">
                    {agent.ai_service.name}
                  </div>
                  <div className="text-xs text-gray-500">
                    {agent.ai_service.model_name} • {agent.ai_service.provider}
                  </div>
                </div>
              ) : (
                <span className="text-gray-400 italic text-sm">No AI Service</span>
              )
            )
          },
          {
            header: 'Status',
            render: () => (
              <span className="inline-flex items-center px-2 py-1 text-xs font-semibold rounded-full bg-green-100 text-green-800">
                <span className="w-2 h-2 bg-green-400 rounded-full mr-2" />
                {' '}Active
              </span>
            )
          },
          {
            header: 'Usage',
            render: (agent) => (
              <div className="text-sm text-gray-900">
                <div className="flex items-center">
                  <span className="font-medium">{agent.request_count}</span>
                  <span className="text-gray-500 ml-1">requests</span>
                </div>
                {agent.request_count > 0 && (
                  <div className="text-xs text-gray-500">
                    Last used: {formatDate(agent.created_at)}
                  </div>
                )}
              </div>
            )
          },
          {
            header: 'Created',
            render: (agent) => formatDate(agent.created_at),
            className: 'px-6 py-4 whitespace-nowrap text-sm text-gray-500'
          },
          {
            header: 'Actions',
            headerClassName: 'px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider',
            className: 'px-6 py-4 whitespace-nowrap text-right text-sm font-medium',
            render: (agent) => (
              <ActionDropdown
                actions={[
                  {
                    label: 'Playground',
                    onClick: () => handlePlayground(agent.agent_id),
                    icon: '🎮',
                    variant: 'warning'
                  },
                  ...(canEdit ? [
                    {
                      label: 'Export',
                      onClick: () => handleExportClick(agent),
                      icon: '⬇️',
                      variant: 'secondary' as const
                    },
                    {
                      label: 'Edit',
                      onClick: () => handleEditAgent(agent.agent_id),
                      icon: '✏️',
                      variant: 'primary' as const
                    },
                    {
                      label: 'Delete',
                      onClick: () => handleDeleteAgent(agent),
                      icon: '🗑️',
                      variant: 'danger' as const
                    }
                  ] : [])
                ]}
                size="sm"
              />
            )
          }
        ]}
        emptyIcon="🤖"
        emptyMessage="No Agents Yet"
        emptySubMessage="Create your first AI agent to get started with intelligent automation."
        loading={loading}
      />

      {!loading && canEdit && agents.length === 0 && (
        <div className="text-center py-6">
          <button 
            onClick={handleCreateAgent}
            className="bg-blue-600 hover:bg-blue-700 text-white px-6 py-3 rounded-lg"
          >
            Create Your First Agent
          </button>
        </div>
      )}

      {/* Delete Confirmation Modal */}
      {showDeleteModal && agentToDelete && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 max-w-md w-full mx-4">
            <h3 className="text-lg font-semibold text-gray-900 mb-4">Delete Agent</h3>
            <p className="text-gray-600 mb-4">
              Are you sure you want to delete "{agentToDelete.name}"? This action cannot be undone.
            </p>

            {/* MCP Usage Warning */}
            {loadingMcpUsage && (
              <div className="mb-4 flex items-center text-gray-500">
                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-gray-500 mr-2"></div>
                Checking MCP server usage...
              </div>
            )}

            {deleteAgentMcpUsage && deleteAgentMcpUsage.mcp_servers.length > 0 && (
              <div className="mb-4 bg-amber-50 border border-amber-200 rounded-lg p-3">
                <div className="flex items-start">
                  <span className="text-amber-500 mr-2">!</span>
                  <div className="text-sm">
                    <p className="font-medium text-amber-900">
                      This agent is used in {deleteAgentMcpUsage.mcp_servers.length} MCP server{deleteAgentMcpUsage.mcp_servers.length !== 1 ? 's' : ''}:
                    </p>
                    <ul className="mt-1 text-amber-800 list-disc list-inside">
                      {deleteAgentMcpUsage.mcp_servers.map(s => (
                        <li key={s.server_id}>{s.server_name}</li>
                      ))}
                    </ul>
                    <p className="mt-2 text-amber-700">
                      Deleting this agent will make it unavailable in these MCP servers.
                    </p>
                  </div>
                </div>
              </div>
            )}

            <div className="flex space-x-3">
              <button
                onClick={() => {
                  setShowDeleteModal(false);
                  setAgentToDelete(null);
                  setDeleteAgentMcpUsage(null);
                }}
                className="flex-1 bg-gray-300 hover:bg-gray-400 text-gray-800 py-2 px-4 rounded-lg"
              >
                Cancel
              </button>
              <button
                onClick={confirmDeleteAgent}
                disabled={loadingMcpUsage}
                className="flex-1 bg-red-600 hover:bg-red-700 disabled:bg-red-400 text-white py-2 px-4 rounded-lg"
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Export Dialog */}
      {showExportDialog && agentToExport && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 max-w-md w-full mx-4">
            <h3 className="text-lg font-semibold text-gray-900 mb-4">Export Agent</h3>
            <p className="text-gray-600 mb-4">
              Exporting "{agentToExport.name}". Select which components to bundle:
            </p>

            {/* Export Options */}
            <div className="space-y-3 mb-4">
              <label className="flex items-center space-x-2">
                <input
                  type="checkbox"
                  checked={exportOptions.includeAIService}
                  onChange={(e) => setExportOptions({...exportOptions, includeAIService: e.target.checked})}
                  className="rounded border-gray-300"
                />
                <span className="text-sm text-gray-700">Include AI Service</span>
              </label>
              <label className="flex items-center space-x-2">
                <input
                  type="checkbox"
                  checked={exportOptions.includeSilo}
                  onChange={(e) => setExportOptions({...exportOptions, includeSilo: e.target.checked})}
                  className="rounded border-gray-300"
                />
                <span className="text-sm text-gray-700">Include Silo (Knowledge Base)</span>
              </label>
              <label className="flex items-center space-x-2">
                <input
                  type="checkbox"
                  checked={exportOptions.includeOutputParser}
                  onChange={(e) => setExportOptions({...exportOptions, includeOutputParser: e.target.checked})}
                  className="rounded border-gray-300"
                />
                <span className="text-sm text-gray-700">Include Output Parser</span>
              </label>
              <label className="flex items-center space-x-2">
                <input
                  type="checkbox"
                  checked={exportOptions.includeMCPConfigs}
                  onChange={(e) => setExportOptions({...exportOptions, includeMCPConfigs: e.target.checked})}
                  className="rounded border-gray-300"
                />
                <span className="text-sm text-gray-700">Include MCP Configs</span>
              </label>
              <label className="flex items-center space-x-2">
                <input
                  type="checkbox"
                  checked={exportOptions.includeAgentTools}
                  onChange={(e) => setExportOptions({...exportOptions, includeAgentTools: e.target.checked})}
                  className="rounded border-gray-300"
                />
                <span className="text-sm text-gray-700">Include Agent Tools</span>
              </label>
            </div>

            <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 mb-4">
              <div className="flex items-start">
                <span className="text-amber-500 mr-2">⚠️</span>
                <p className="text-sm text-amber-800">
                  Conversation history is NOT exported. Only configuration is included.
                </p>
              </div>
            </div>

            <div className="flex space-x-3">
              <button
                onClick={() => {
                  setShowExportDialog(false);
                  setAgentToExport(null);
                }}
                className="flex-1 bg-gray-300 hover:bg-gray-400 text-gray-800 py-2 px-4 rounded-lg"
              >
                Cancel
              </button>
              <button
                onClick={handleExport}
                className="flex-1 bg-blue-600 hover:bg-blue-700 text-white py-2 px-4 rounded-lg"
              >
                Export
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Import Modal */}
      {showImportModal && (
        <ImportModal
          isOpen={showImportModal}
          onClose={() => {
            setShowImportModal(false);
            setRequiresAIServiceSelection(false);
            setSelectedAIServiceId(undefined);
          }}
          onImport={handleImport}
          componentType="agent"
          componentLabel="Agent"
          additionalContent={
            requiresAIServiceSelection && availableAIServices.length > 0 ? (
              <div className="mb-4">
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Select AI Service (Required)
                </label>
                <select
                  value={selectedAIServiceId || ''}
                  onChange={(e) => setSelectedAIServiceId(Number(e.target.value))}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2"
                >
                  <option value="">-- Select AI Service --</option>
                  {availableAIServices.map((svc) => (
                    <option key={svc.id} value={svc.id}>
                      {svc.name}
                    </option>
                  ))}
                </select>
                <p className="text-sm text-gray-500 mt-1">
                  This agent requires an AI service that is not bundled in the export file.
                </p>
              </div>
            ) : null
          }
        />
      )}
    </div>
  );
}

export default AgentsPage; 