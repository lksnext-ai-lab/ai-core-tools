import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { toast } from 'sonner';
import { Bot, ArrowUp, ArrowDownToLine, Gamepad2, Pencil, Trash2, FileText, ArrowUpRight } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { apiService } from '../services/api';
import ActionDropdown from '../components/ui/ActionDropdown';
import Alert from '../components/ui/Alert';
import Table from '../components/ui/Table';
import { useAppRole } from '../hooks/useAppRole';
import { AppRole } from '../types/roles';
import ReadOnlyBanner from '../components/ui/ReadOnlyBanner';
import AgentImportStepper from '../components/import/AgentImportStepper';
import { useConfirm } from '../contexts/ConfirmContext';
import { useApiMutation } from '../hooks/useApiMutation';
import { errorMessage } from '../constants/messages';
import type { AgentMCPUsage } from '../core/types';
import type { ServiceLifecycleWarning } from '../types/services';
import ServiceLifecycleAlert from '../components/services/ServiceLifecycleAlert';
import Title from '../components/ui/Title';
import LoadingState from '../components/ui/LoadingState';
import ButtonApp from '../components/ui/ButtonApp';
import BackgroundImage from '../components/ui/BackgroundImage';
import { FormCheckbox } from '../components/ui/FormField';
import { useTranslation } from 'react-i18next';


// Define the Agent type
interface Agent {
  agent_id: number;
  name: string;
  type: string;
  is_tool: boolean;
  a2a_enabled?: boolean;
  created_at: string;
  request_count: number;
  description?: string;
  service_id?: number;
  ai_service?: {
    name: string;
    model_name: string;
    provider: string;
  };
  lifecycle_warnings?: ServiceLifecycleWarning[];
}

// Define the App type
interface App {
  app_id: number;
  name: string;
}

function AgentsPage() {
  const { appId } = useParams();
  const navigate = useNavigate();
  const { t, i18n } = useTranslation('common');
  const { hasMinRole, userRole } = useAppRole(appId);
  const canEdit = hasMinRole(AppRole.EDITOR);
  const confirm = useConfirm();
  const mutate = useApiMutation();

  const [agents, setAgents] = useState<Agent[]>([]);
  const [scheduledTaskCounts, setScheduledTaskCounts] = useState<Record<number, number>>({});
  const [app, setApp] = useState<App | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
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

  const loadData = useCallback(async () => {
    if (!appId) return;
    
    try {
      setLoading(true);
      setError(null);
      
      const [agentsResponse, appResponse] = await Promise.all([
        apiService.getAgents(Number.parseInt(appId)),
        apiService.getApp(Number.parseInt(appId))
      ]);
      
      setAgents(agentsResponse);
      setApp(appResponse);
      try {
        const tasks = await apiService.getScheduledTasks(Number.parseInt(appId));
        const counts = tasks.reduce<Record<number, number>>((result, task) => {
          result[task.agent_id] = (result[task.agent_id] ?? 0) + 1;
          return result;
        }, {});
        setScheduledTaskCounts(counts);
      } catch {
        // Keep the agent list usable when the scheduled-task API is unavailable.
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : i18n.t('agentsPage.loadFailed'));
      console.error('Error loading data:', err);
    } finally {
      setLoading(false);
    }
  }, [appId, i18n]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

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

    let mcpUsage: AgentMCPUsage | null = null;
    if (agent.is_tool) {
      try {
        mcpUsage = await apiService.getAgentMCPUsage(Number.parseInt(appId), agent.agent_id);
      } catch (err) {
        console.error('Error loading MCP usage:', err);
      }
    }

    const message = (
      <div className="space-y-3">
        <p>{t('agentsPage.delete.confirmText', { name: agent.name })}</p>
        {mcpUsage && mcpUsage.mcp_servers.length > 0 && (
          <Alert
            type="warning"
            title={t('agentsPage.delete.usedInMcpServers', { count: mcpUsage.mcp_servers.length })}
            message={(
              <>
                <ul className="list-disc list-inside">
                  {mcpUsage.mcp_servers.map((s) => (
                    <li key={s.server_id}>{s.server_name}</li>
                  ))}
                </ul>
                <p className="mt-2">
                  {t('agentsPage.delete.mcpWarning')}
                </p>
              </>
            )}
          />
        )}
      </div>
    );

    const ok = await confirm({
      title: t('agentsPage.delete.confirmTitle'),
      message,
      variant: 'danger',
      confirmLabel: t('delete'),
    });
    if (!ok) return;

    const result = await mutate(
      () => apiService.deleteAgent(Number.parseInt(appId), agent.agent_id),
      {
        loading: t('agentsPage.delete.loading'),
        success: t('agentsPage.delete.success'),
        error: (err) => errorMessage(err, t('agentsPage.delete.failed')),
      },
    );
    if (result === undefined) return;

    setAgents(agents.filter((a) => a.agent_id !== agent.agent_id));
  };

  const handleExportClick = (agent: Agent) => {
    setAgentToExport(agent);
    setShowExportDialog(true);
  };

  const handleExport = async () => {
    if (!agentToExport || !appId) return;

    try {
      const blob = await apiService.exportAgent(
        Number.parseInt(appId),
        agentToExport.agent_id,
        exportOptions.includeAIService,
        exportOptions.includeSilo,
        exportOptions.includeOutputParser,
        exportOptions.includeMCPConfigs,
        exportOptions.includeAgentTools
      );
      
      // Generate filename
      const timestamp = new Date().toISOString().split('T')[0];
      const sanitizedName = agentToExport.name.replaceAll(/[^a-z0-9]/gi, '_').toLowerCase();
      const filename = `agent-${sanitizedName}-${timestamp}.json`;
      
      // Download
      const url = globalThis.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      globalThis.URL.revokeObjectURL(url);
      a.remove();

      setShowExportDialog(false);
      setAgentToExport(null);
      toast.warning(t('agentsPage.export.successWarning'), {
        duration: 7000,
      });
    } catch (err) {
      toast.error(errorMessage(err, t('agentsPage.export.failed')));
      console.error('Error exporting agent:', err);
    }
  };

  const handleImportComplete = () => {
    setShowImportModal(false);
    toast.success(t('agentsPage.import.success'));
    void loadData();
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString(i18n.resolvedLanguage);
  };

  const getAgentTypeIcon = (type: string): LucideIcon => {
    switch (type) {
      case 'ocr_agent':
        return FileText;
      case 'agent':
      default:
        return Bot;
    }
  };

  const getAgentTypeLabel = (type: string) => {
    switch (type) {
      case 'ocr_agent':
        return t('agentsPage.agentTypes.ocr');
      case 'agent':
      default:
        return t('agentsPage.agentTypes.ai');
    }
  };

  if (loading) {
    return (
      <div className="space-y-6">
        {/* Page Header */}
        <div className="flex items-center justify-between">
         <Title
            titulo={t('agentsPage.title')}
            subtitulo={t('agentsPage.subtitle', { app: app?.name || appId })}
            variant="titSecundario"
            titleMarginBottom={6}
            subtitleMarginBottom={0}
          />
        </div>

        <LoadingState variant="page" message={t('agentsPage.loading')} />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        {/*<div>
          <h1 className="text-2xl font-bold text-gray-900">Agents</h1>
          <p className="text-gray-600">Manage your AI agents for app {app?.name || appId}</p>
        </div>*/}
        <Title
          titulo={t('agentsPage.title')}
          subtitulo={t('agentsPage.subtitle', { app: app?.name || appId })}
          variant="titSecundario"
          titleMarginBottom={6}
          subtitleMarginBottom={0}
        />
        <div className="flex items-center space-x-3">
          {hasMinRole(AppRole.ADMINISTRATOR) && (
            <ButtonApp
              label={t('agentsPage.importAgent')}
              variant="secondary"
              size="medium"
              icon={<ArrowUp className="h-4 w-4" aria-hidden="true" />}
              onClick={() => setShowImportModal(true)}
            />
          )}
          {canEdit && (
            <ButtonApp
              label={`+ ${t('agentsPage.createAgent')}`}
              variant="primary"
              size="medium"
              onClick={handleCreateAgent}
            />
          )}
        </div>
      </div>

      {!canEdit && <ReadOnlyBanner userRole={userRole} minRole={AppRole.EDITOR} />}

      {/* Error Message */}
      {error && <Alert type="error" message={error} onDismiss={() => setError(null)} />}

      <Table
        data={agents}
        stickyEdgeColumns
        keyExtractor={(agent) => agent.agent_id.toString()}
        columns={[
          {
            header: t('agentsPage.columns.agent'),
            render: (agent) => (
              <div className="flex items-center">
                <BackgroundImage
                  icon={getAgentTypeIcon(agent.type)}
                  size={28}
                  iconSize={14}
                  variant="marron"
                  className="rounded-lg"
                />
                <div className="ml-4">
                  <div className="text-sm font-medium text-gray-900">
                    {canEdit ? (
                      <Link 
                        to={`/apps/${appId}/agents/${agent.agent_id}`} 
                        className="text-sm font-medium text-fg dark:text-fg-dark"
                      >
                        {agent.name}
                      </Link>
                    ) : (
                      <span className="text-sm font-medium text-fg dark:text-fg-dark">
                        {agent.name}
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-1 flex-wrap mt-0.5">
                    {agent.is_tool && (
                      <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-yellow-100 text-yellow-800 dark:bg-yellow-900/40 dark:text-yellow-200">
                        {t('agentsPage.tool')}
                      </span>
                    )}
                    {agent.a2a_enabled && (
                      <span
                        className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-indigo-100 text-indigo-800 dark:bg-indigo-900/40 dark:text-indigo-200"
                        aria-label={t('agentsPage.exposedViaA2A')}
                      >
                        A2A
                      </span>
                    )}
                    <ServiceLifecycleAlert warnings={agent.lifecycle_warnings} variant="compact" />
                  </div>
                </div>
              </div>
            )
          },
          {
            header: t('agentsPage.columns.description'),
            render: (agent) => (
              <div className="text-xs text-fg-secondary dark:text-fg-secondary-dark max-w-xs">
                {agent.description ? (
                  <div className="truncate" title={agent.description}>
                    {agent.description}
                  </div>
                ) : (
                  <span className="text-fg-secondary dark:text-fg-secondary-dark italic">{t('agentsPage.noDescription')}</span>
                )}
              </div>
            ),
            className: 'px-6 py-4'
          },
          {
            header: t('agentsPage.columns.type'),
            render: (agent) => (
              <span className="text-xs text-fg-secondary dark:text-fg-secondary-dark">
                {getAgentTypeLabel(agent.type)}
              </span>
            )
          },
          {
            header: t('agentsPage.columns.aiService'),
            render: (agent) => (
              agent.ai_service ? (
                <div className="text-sm">
                  <div className="font-medium text-fg dark:text-fg-dark">
                    {agent.ai_service.name}
                  </div>
                  <div className="text-xs text-fg-secondary dark:text-fg-secondary-dark">
                    {agent.ai_service.model_name} • {agent.ai_service.provider}
                  </div>
                </div>
              ) : (
                <span className="text-fg-secondary dark:text-fg-secondary-dark italic text-sm">{t('agentsPage.noAIService')}</span>
              )
            )
          },
          {
            header: t('agentsPage.columns.status'),
            render: () => (
              <span className="inline-flex items-center justify-center px-[9px] py-[3px] text-[11.5px] rounded-[200px] w-24 bg-success-bg text-success">
                {' '}{t('agentsPage.active')}
              </span>
            )
          },
          {
            header: t('agentsPage.columns.scheduling'),
            render: (agent) => {
              const count = scheduledTaskCounts[agent.agent_id] ?? 0;
              if (!count) return <span className="text-fg-secondary dark:text-fg-secondary-dark text-xs">—</span>;
              return (
                <button
                  type="button"
                  onClick={() => navigate(`/apps/${appId}/scheduled-tasks?agent_id=${agent.agent_id}`)}
                  className="text-xs text-bronze  dark:text-bronze-dark inline-block"
                  title={t('agentsPage.scheduling.openTitle')}
                >
                  {t('agentsPage.scheduling.usedByTask', { count })}
                  {''}<ArrowUpRight className="w-4 h-4 inline-block ml-1" aria-hidden="true" />

                </button>
              );
            }
          },
          {
            header: t('agentsPage.columns.usage'),
            render: (agent) => (
              <div className="text-fg-secondary dark:text-fg-secondary-dark text-sm">
                <div className="flex items-center">
                  <span className="font-medium">{agent.request_count}</span>
                  <span className="text-xs text-fg-secondary dark:text-fg-secondary-dark ml-1">{t('agentsPage.requests')}</span>
                </div>
                {agent.request_count > 0 && (
                  <div className="text-xs text-fg-secondary dark:text-fg-secondary-dark">
                    {t('agentsPage.lastUsed', { date: formatDate(agent.created_at) })}
                  </div>
                )}
              </div>
            )
          },
          {
            header: t('agentsPage.columns.created'),
            render: (agent) => formatDate(agent.created_at),
            className: 'px-6 py-4 whitespace-nowrap text-xs text-fg-secondary dark:text-fg-secondary-dark'
          },
          {
            header: t('agentsPage.columns.actions'),
            sticky: 'right',
            headerClassName: 'px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider',
            className: 'px-6 py-4 whitespace-nowrap text-right text-sm font-medium',
            render: (agent) => (
              <ActionDropdown
                triggerText={t('agentsPage.columns.actions')}
                actions={[
                  {
                    label: t('agentsPage.actions.playground'),
                    onClick: () => handlePlayground(agent.agent_id),
                    icon: <Gamepad2 className="w-4 h-4" />,
                    variant: 'warning'
                  },
                  ...(canEdit ? [
                    {
                      label: t('agentsPage.actions.export'),
                      onClick: () => handleExportClick(agent),
                      icon: <ArrowDownToLine className="w-4 h-4" />,
                      variant: 'primary' as const
                    },
                    {
                      label: t('edit'),
                      onClick: () => handleEditAgent(agent.agent_id),
                      icon: <Pencil className="w-4 h-4" />,
                      variant: 'primary' as const
                    },
                    {
                      label: t('delete'),
                      onClick: () => { void handleDeleteAgent(agent); },
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
        emptyIcon={<BackgroundImage icon={Bot} size={64} iconSize={32} />}
        emptyMessage={t('agentsPage.empty.title')}
        emptySubMessage={t('agentsPage.empty.subtitle')}
        loading={loading}
      />

      {!loading && canEdit && agents.length === 0 && (
        <div className="text-center py-6">
          <ButtonApp
            label={t('agentsPage.empty.createFirstAgent')}
            onClick={handleCreateAgent}
            variant="primary"
            size="medium"
          />
        </div>
      )}

      {/* Export Dialog */}
      {showExportDialog && agentToExport && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-md p-6 max-w-md w-full mx-4">
            <h3 className="text-lg font-semibold text-fg dark:text-fg-dark mb-4">{t('agentsPage.export.title')}</h3>
            <p className="text-fg-secondary dark:text-fg-secondary-dark mb-4">
              {t('agentsPage.export.description', { name: agentToExport.name })}
            </p>

            {/* Export Options */}
            <div className="space-y-3 mb-4">
              <FormCheckbox
                id="include-ai-service"
                label={t('agentsPage.export.includeAIService')}
                checked={exportOptions.includeAIService}
                onChange={(e) => setExportOptions({ ...exportOptions, includeAIService: e.target.checked })}
              />
              <FormCheckbox
                id="include-silo"
                label={t('agentsPage.export.includeSilo')}
                checked={exportOptions.includeSilo}
                onChange={(e) => setExportOptions({ ...exportOptions, includeSilo: e.target.checked })}
              />
              <FormCheckbox
                id="include-output-parser"
                label={t('agentsPage.export.includeOutputParser')}
                checked={exportOptions.includeOutputParser}
                onChange={(e) => setExportOptions({ ...exportOptions, includeOutputParser: e.target.checked })}
              />
              <FormCheckbox
                id="include-mcp-configs"
                label={t('agentsPage.export.includeMCPConfigs')}
                checked={exportOptions.includeMCPConfigs}
                onChange={(e) => setExportOptions({ ...exportOptions, includeMCPConfigs: e.target.checked })}
              />
              <FormCheckbox
                id="include-agent-tools"
                label={t('agentsPage.export.includeAgentTools')}
                checked={exportOptions.includeAgentTools}
                onChange={(e) => setExportOptions({ ...exportOptions, includeAgentTools: e.target.checked })}
              />
            </div>

            <Alert
              type="warning"
              className="mb-4"
              message={t('agentsPage.export.historyNotIncluded')}
            />

            <div className="flex space-x-3">
              <ButtonApp
                label={t('cancel')}
                variant="secondary"
                size="medium"
                onClick={() => {
                  setShowExportDialog(false);
                  setAgentToExport(null);
                }}
                className="flex-1"
              />
              <ButtonApp
                label={t('agentsPage.actions.export')}
                variant="primary"
                size="medium"
                onClick={handleExport}
                className="flex-1"
              />
            </div>
          </div>
        </div>
      )}

      {/* Import Stepper */}
      {showImportModal && (
        <AgentImportStepper
          appId={Number.parseInt(appId!)}
          isOpen={showImportModal}
          onClose={() => setShowImportModal(false)}
          onImportComplete={handleImportComplete}
        />
      )}
    </div>
  );
}

export default AgentsPage;
