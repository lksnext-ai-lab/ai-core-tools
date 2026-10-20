import { useParams } from 'react-router-dom';
import { useState } from 'react';
import { Bot, Plug, ArrowDownToLine, ClipboardCopy, Pencil, Trash2, Upload, AlertTriangle } from 'lucide-react';
import Modal from '../../components/ui/Modal';
import ServiceWizard from '../../components/services/wizard/ServiceWizard';
import CompactServiceEditor from '../../components/services/CompactServiceEditor';
import ActionDropdown from '../../components/ui/ActionDropdown';
import ImportModal, { type ImportResponse, type ConflictMode } from '../../components/ui/ImportModal';
import { useSettingsCache } from '../../contexts/SettingsCacheContext';
import { useAppRole } from '../../hooks/useAppRole';
import ReadOnlyBanner from '../../components/ui/ReadOnlyBanner';
import Alert from '../../components/ui/Alert';
import Table from '../../components/ui/Table';
import { useServicesManager } from '../../hooks/useServicesManager';
import { Badge, ProviderBadge } from '../../components/ui/Badge';
import { AppRole } from '../../types/roles';
import { LoadingState } from '../../components/ui/LoadingState';
import { Spinner } from '../../components/ui/Spinner';
import { Title } from '../../components/ui/Title';
import { ButtonApp } from '../../components/ui/ButtonApp';
import BackgroundImage from '../../components/ui/BackgroundImage';

interface AIService {
  service_id: number;
  name: string;
  provider: string;
  model_name: string;
  created_at: string;
  needs_api_key?: boolean;
}

function AIServicesPage() {
  const { appId } = useParams();
  const settingsCache = useSettingsCache();
  const { hasMinRole, userRole } = useAppRole(appId);
  const canEdit = hasMinRole(AppRole.ADMINISTRATOR);

  const api = {
    getAll: (id: number) => import('../../services/api').then(m => m.apiService.getAIServices(id)),
    getOne: (id: number, sid: number) => import('../../services/api').then(m => m.apiService.getAIService(id, sid)),
    create: (id: number, data: any) => import('../../services/api').then(m => m.apiService.createAIService(id, data)),
    update: (id: number, sid: number, data: any) => import('../../services/api').then(m => m.apiService.updateAIService(id, sid, data)),
    delete: (id: number, sid: number) => import('../../services/api').then(m => m.apiService.deleteAIService(id, sid)),
    copy: (id: number, sid: number) => import('../../services/api').then(m => m.apiService.copyAIService(id, sid)),
  };

  const cache = {
    get: (id: string) => settingsCache.getAIServices(id),
    set: (id: string, data: any[]) => settingsCache.setAIServices(id, data),
    invalidate: (id: string) => settingsCache.invalidateAIServices(id),
  };

  const {
    services,
    loading,
    error,
    isModalOpen,
    editingService,
    handleClose,
    handleCreate,
    handleDelete,
    handleEdit,
    handleCopy,
    handleSave,
    setIsModalOpen,
    setEditingService,
    forceReload,
  } = useServicesManager<AIService>(appId, api as any, cache as any, { entity: 'AI service' });

  const [testResult, setTestResult] = useState<any>(null);
  const [isTestModalOpen, setIsTestModalOpen] = useState(false);
  const [testingServiceId, setTestingServiceId] = useState<number | null>(null);
  const [showImportModal, setShowImportModal] = useState(false);
  const [exportingServiceId, setExportingServiceId] = useState<number | null>(null);
  const [notification, setNotification] = useState<{message: string; type: 'success' | 'error'} | null>(null);

  async function handleTestConnection(serviceId: number) {
    if (!appId) return;
    setTestingServiceId(serviceId);
    setTestResult(null);
    setIsTestModalOpen(true);
    
    try {
      const apiService = (await import('../../services/api')).apiService;
      const result = await apiService.testAIServiceConnection(Number.parseInt(appId), serviceId);
      setTestResult(result);
    } catch (err) {
      setTestResult({ status: 'error', message: err instanceof Error ? err.message : 'Failed to test connection' });
    } finally {
      setTestingServiceId(null);
    }
  }

  async function handleExport(serviceId: number) {
    if (!appId) return;
    setExportingServiceId(serviceId);
    
    try {
      const apiService = (await import('../../services/api')).apiService;
      const blob = await apiService.exportAIService(Number.parseInt(appId), serviceId);
      
      // Find service name for filename
      const service = services.find(s => s.service_id === serviceId);
      const serviceName = service?.name || 'ai-service';
      const sanitizedName = serviceName.replaceAll(/[^a-z0-9]/gi, '-').toLowerCase();
      const timestamp = new Date().toISOString().split('T')[0];
      const filename = `ai-service-${sanitizedName}-${timestamp}.json`;
      
      // Create download link
      const url = globalThis.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      globalThis.URL.revokeObjectURL(url);
      a.remove();
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to export service');
    } finally {
      setExportingServiceId(null);
    }
  }

  async function handleImport(
    file: File,
    conflictMode: ConflictMode,
    newName?: string
  ): Promise<ImportResponse> {
    if (!appId) throw new Error('App ID not found');
    
    try {
      const apiService = (await import('../../services/api')).apiService;
      const result = await apiService.importAIService(
        Number.parseInt(appId),
        file,
        conflictMode,
        newName
      );
      
      if (result.success) {
        // Close modal immediately
        setShowImportModal(false);
        // Show success notification
        setNotification({
          message: result.message || 'Import completed successfully',
          type: 'success'
        });
        // Refresh the list
        void forceReload();
        // Auto-dismiss notification after 5 seconds
        setTimeout(() => setNotification(null), 5000);
      }
      
      return result;
    } catch (err) {
      // Show error notification
      setNotification({
        message: err instanceof Error ? err.message : 'Import failed',
        type: 'error'
      });
      setTimeout(() => setNotification(null), 5000);
      // Re-throw the error so ImportModal can catch it
      throw err;
    }
  }

  if (loading) return (
    <LoadingState variant="page" message="Loading AI services..." />
  );

  if (error) return (
    <div className="p-6">
      <Alert type="error" message={error} onDismiss={() => { setIsModalOpen(false); setEditingService(null); }} />
    </div>
  );

  return (
    <div className="p-6">
      {/* Header */}
      <div className="flex justify-between items-center mb-6">
        <Title variant='titSecundario' titulo='Ai Services' subtitulo='Manage language models and AI providers for your agents'></Title>
        {canEdit && (
          <div className="flex gap-2">
            <ButtonApp
              label="Import"
              onClick={() => setShowImportModal(true)}
              icon={<Upload className="w-4 h-4" aria-hidden="true" />}
              variant="secondary"
              size="medium"
            />
            <ButtonApp
              label="Add AI Service"
              onClick={handleCreate}
              icon={<span aria-hidden="true">+</span>}
              variant="primary"
              size="medium"
            />
          </div>
        )}
      </div>

      {!canEdit && <ReadOnlyBanner userRole={userRole} minRole={AppRole.ADMINISTRATOR} />}

      <Table
        data={services}
        keyExtractor={(service) => (service as any).service_id.toString()}
        columns={[
          {
            header: 'Name',
            render: (service: AIService) => (
              <div className="flex items-center gap-2">
              <BackgroundImage icon={Bot} variant="marron" />
              {canEdit ? (
                
                <button type="button" className="text-sm font-medium text-fg dark:text-fg-dark text-left" onClick={() => handleEdit(service.service_id)}>
                  {service.name}
                </button>
              ) : (
                <span className="text-sm font-medium text-fg dark:text-fg-dark">{service.name}</span>
              )}
              </div>
            )            
          },
          { header: 'Model', accessor: 'model_name', className: 'text-xs font-medium text-fg-secondary dark:text-fg-secondary-dark' },
          { header: 'Provider', render: (service: AIService) => (
            <ProviderBadge provider={service.provider} />
          )},
          { header: 'Status', render: (service: AIService) => (
            service.needs_api_key ? (
              <Badge
                label="API Key Required"
                variant="warning"
                icon={<AlertTriangle className="w-3 h-3" aria-hidden="true" />}
              />
            ) : (
              <Badge label="Ready" variant="success" />
            )
          )},
          { header: 'Created', className:'text-xs text-fg-secondary dark:text-fg-secondary-dark', render: (service: any) => (service.created_at ? new Date(service.created_at).toLocaleDateString() : 'N/A') },
          { header: 'Actions', className: 'relative', render: (service: AIService) => (
            canEdit ? (
              <ActionDropdown actions={[
                {
                  label: testingServiceId === service.service_id ? 'Testing...' : 'Test Connection',
                  onClick: () => void handleTestConnection(service.service_id),
                  icon: testingServiceId === service.service_id ? <Spinner size="sm" tone="current" /> : <Plug className="w-4 h-4" />,
                  disabled: testingServiceId === service.service_id
                },
                {
                  label: exportingServiceId === service.service_id ? 'Exporting...' : 'Export',
                  onClick: () => void handleExport(service.service_id),
                  icon: exportingServiceId === service.service_id ? <Spinner size="sm" tone="current" /> : <ArrowDownToLine className="w-4 h-4" />,
                  variant: 'primary' as const,
                  disabled: exportingServiceId === service.service_id
                },
                { label: 'Edit', onClick: () => void handleEdit(service.service_id), icon: <Pencil className="w-4 h-4" />, variant: 'primary' as const },
                { label: 'Copy', onClick: () => void handleCopy(service.service_id), icon: <ClipboardCopy className="w-4 h-4" />, variant: 'primary' as const },
                { label: 'Delete', onClick: () => void handleDelete(service.service_id), icon: <Trash2 className="w-4 h-4" />, variant: 'danger' as const }
              ]} size="sm" />
            ) : (
               <span className="text-gray-400 text-sm">View only</span>
            )
          ) }
        ]}
        emptyIcon={<Bot className="w-10 h-10 text-gray-300" />}
        emptyMessage="No AI Services"
        emptySubMessage="Add your first AI service to start using language models in your agents."
        loading={loading}
      />

      {!loading && services.length === 0 && canEdit && (
        <div className="text-center py-6">
          <button onClick={handleCreate} className="bg-blue-600 hover:bg-blue-700 text-white px-6 py-3 rounded-lg">Add First AI Service</button>
        </div>
      )}

      {notification && (
        <Alert
          type={notification.type}
          message={notification.message}
          onDismiss={() => setNotification(null)}
          className="mb-4"
        />
      )}

      <Alert
        type="info"
        title="About AI Services"
        className="mt-6"
        message="AI Services define the language models your agents can use. Configure OpenAI, Azure OpenAI, Anthropic Claude, or local models like Ollama. Each service requires proper authentication and endpoint configuration."
      />

      {isModalOpen && !editingService && (
        <ServiceWizard
          isOpen
          kind="ai"
          scope="app"
          appId={appId ? Number.parseInt(appId) : undefined}
          existingNames={services.map((s) => s.name)}
          onClose={handleClose}
          onSave={handleSave}
        />
      )}

      {isModalOpen && editingService && (
        <CompactServiceEditor
          isOpen
          kind="ai"
          scope="app"
          appId={appId ? Number.parseInt(appId) : undefined}
          service={editingService}
          existingNames={services.map((s) => s.name)}
          onClose={handleClose}
          onSave={handleSave}
        />
      )}

      {/* Test Result Modal */}
      <Modal
        isOpen={isTestModalOpen}
        onClose={() => !testingServiceId && setIsTestModalOpen(false)}
        title="Connection Test Result"
      >
        <div className="p-4">
          {testingServiceId ? (
            <LoadingState variant="section" message="Testing connection to AI service..." />
          ) : testResult && (
            <div>
              <Alert
                type={testResult.status === 'success' ? 'success' : 'error'}
                title={`Status: ${testResult.status === 'success' ? 'Success' : 'Error'}`}
                message={(
                  <div className="space-y-2">
                    <p><strong>Message:</strong> {testResult.message}</p>
                    {testResult.response && (
                      <div>
                        <h4 className="font-semibold mb-2">Response:</h4>
                        <div className="bg-gray-50 p-3 rounded border text-sm font-mono whitespace-pre-wrap max-h-60 overflow-y-auto">
                          {testResult.response}
                        </div>
                      </div>
                    )}
                  </div>
                )}
              />
            </div>
          )}
          {!testingServiceId && (
            <div className="mt-4 flex justify-end">
              <ButtonApp
                label="Close"
                onClick={() => setIsTestModalOpen(false)}
                variant="secondary"
                size="medium"
              />
            </div>
          )}
        </div>
      </Modal>

      {/* Import Modal */}
      <ImportModal
        isOpen={showImportModal}
        onClose={() => setShowImportModal(false)}
        onImport={handleImport}
        componentType="ai_service"
        componentLabel="AI Service"
      />
    </div>
  );
}

export default AIServicesPage;