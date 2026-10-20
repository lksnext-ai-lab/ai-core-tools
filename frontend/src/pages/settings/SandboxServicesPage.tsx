import { useParams } from 'react-router-dom';
import { useState } from 'react';
import { Box, Plug, Pencil, ClipboardCopy, Trash2, AlertTriangle } from 'lucide-react';
import Modal from '../../components/ui/Modal';
import ServiceWizard from '../../components/services/wizard/ServiceWizard';
import CompactServiceEditor from '../../components/services/CompactServiceEditor';
import ActionDropdown from '../../components/ui/ActionDropdown';
import { useSettingsCache } from '../../contexts/SettingsCacheContext';
import { useAppRole } from '../../hooks/useAppRole';
import ReadOnlyBanner from '../../components/ui/ReadOnlyBanner';
import Alert from '../../components/ui/Alert';
import Table from '../../components/ui/Table';
import { useServicesManager } from '../../hooks/useServicesManager';
import { AppRole } from '../../types/roles';
import { LoadingState } from '../../components/ui/LoadingState';
import { Spinner } from '../../components/ui/Spinner';
import { Title } from '../../components/ui/Title';
import { ButtonApp } from '../../components/ui/ButtonApp';
import BackgroundImage from '../../components/ui/BackgroundImage';
import { Badge, ProviderBadge } from '../..';

interface SandboxService {
  service_id: number;
  name: string;
  provider: string;
  created_at: string;
  needs_api_key?: boolean;
}

function SandboxServicesPage() {
  const { appId } = useParams();
  const settingsCache = useSettingsCache();
  const { hasMinRole, userRole } = useAppRole(appId);
  const canEdit = hasMinRole(AppRole.ADMINISTRATOR);

  const api = {
    getAll: (id: number) => import('../../services/api').then(m => m.apiService.getSandboxServices(id)),
    getOne: (id: number, sid: number) => import('../../services/api').then(m => m.apiService.getSandboxService(id, sid)),
    create: (id: number, data: any) => import('../../services/api').then(m => m.apiService.createSandboxService(id, data)),
    update: (id: number, sid: number, data: any) => import('../../services/api').then(m => m.apiService.updateSandboxService(id, sid, data)),
    delete: (id: number, sid: number) => import('../../services/api').then(m => m.apiService.deleteSandboxService(id, sid)),
    copy: (id: number, sid: number) => import('../../services/api').then(m => m.apiService.copySandboxService(id, sid)),
  };

  const cache = {
    get: (id: string) => settingsCache.getSandboxServices(id),
    set: (id: string, data: any[]) => settingsCache.setSandboxServices(id, data),
    invalidate: (id: string) => settingsCache.invalidateSandboxServices(id),
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
  } = useServicesManager<SandboxService>(appId, api as any, cache as any, { entity: 'sandbox service' });

  const [testResult, setTestResult] = useState<any>(null);
  const [isTestModalOpen, setIsTestModalOpen] = useState(false);
  const [testingServiceId, setTestingServiceId] = useState<number | null>(null);

  async function handleTestConnection(serviceId: number) {
    if (!appId) return;
    setTestingServiceId(serviceId);
    setTestResult(null);
    setIsTestModalOpen(true);

    try {
      const apiService = (await import('../../services/api')).apiService;
      const result = await apiService.testSandboxServiceConnection(Number.parseInt(appId), serviceId);
      setTestResult(result);
    } catch (err) {
      setTestResult({ status: 'error', message: err instanceof Error ? err.message : 'Failed to test connection' });
    } finally {
      setTestingServiceId(null);
    }
  }

  if (loading) return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <Title variant='titSecundario' titulo="Sandbox Services" subtitulo="Manage isolated code-execution environments used by the Code Interpreter capability" />
      </div>
      <LoadingState variant="page" message="Loading sandbox services..." />
    </div>
  );

  if (error) return (
    <div className="p-6">
      <div className="flex items-center justify-between">
        <Title variant='titSecundario' titulo="Sandbox Services" subtitulo="Manage isolated code-execution environments used by the Code Interpreter capability" />
      </div>
      <Alert type="error" message={error} onDismiss={() => { setIsModalOpen(false); setEditingService(null); }} />
    </div>
  );

  return (
    <div className="p-6">
      {/* Header */}
      <div className="flex justify-between items-center mb-6">
        <Title variant='titSecundario' titulo='Sandbox Services' subtitulo='Manage isolated code-execution environments used by the Code Interpreter capability'/>
        {canEdit && (
          <div className="flex gap-2">
            <ButtonApp
              label="Add Sandbox Service"
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
            render: (service: SandboxService) => (
              <div className="flex items-center">
                <BackgroundImage icon={Box} size={28} iconSize={14} variant="marron" className="rounded-lg" />
                <div className="ml-4">
                  {canEdit ? (
                    <button type="button" className="text-sm font-medium text-fg dark:text-fg-dark text-left" onClick={() => handleEdit(service.service_id)}>
                      {service.name}
                    </button>
                  ) : (
                    <span className="text-sm font-medium text-fg dark:text-fg-dark">{service.name}</span>
                  )}
                </div>
              </div>
            )
          },
          { header: 'Provider', render: (service: SandboxService) => (
            <ProviderBadge provider={service.provider} />
            
          )},
          { header: 'Status', render: (service: SandboxService) => (
            service.needs_api_key ? (
              <Badge label="API Key Required" variant="warning" icon={<AlertTriangle className="w-3 h-3" />} />
            ) : (
              <Badge label="Ready" variant="success" />
            )
          )},
          { header: 'Created', className:'text-xs text-fg-secondary dark:text-fg-secondary-dark align-center px-6 py-3', render: (service: any) => (service.created_at ? new Date(service.created_at).toLocaleDateString() : 'N/A') },
          { header: 'Actions', className: 'relative', render: (service: SandboxService) => (
            canEdit ? (
              <ActionDropdown actions={[
                {
                  label: testingServiceId === service.service_id ? 'Testing...' : 'Test Connection',
                  onClick: () => void handleTestConnection(service.service_id),
                  icon: testingServiceId === service.service_id ? <Spinner size="sm" tone="current" /> : <Plug className="w-4 h-4" />,
                  disabled: testingServiceId === service.service_id
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
        emptyIcon={<Box className="w-10 h-10 text-gray-300" />}
        emptyMessage="No Sandbox Services"
        emptySubMessage="Add a sandbox service to let agents run the Code Interpreter capability."
        loading={loading}
      />

      {!loading && services.length === 0 && canEdit && (
        <div className="text-center py-6">
          <ButtonApp
            label="Add First Sandbox Service"
            onClick={handleCreate}
            variant="primary"
            size="medium"
          />
        </div>
      )}

      <Alert
        type="info"
        title="About Sandbox Services"
        className="mt-6"
        message="Sandbox Services configure the isolated environment where agents execute Python code when the Code Interpreter capability is enabled. Configure OpenSandbox (self-hosted container), Daytona, or E2B (managed cloud sandboxes)."
      />

      {isModalOpen && !editingService && (
        <ServiceWizard
          isOpen
          kind="sandbox"
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
          kind="sandbox"
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
            <LoadingState variant="section" message="Testing connection to sandbox service..." />
          ) : testResult && (
            <div>
              <div className={`mb-4 p-3 rounded ${testResult.status === 'success' ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'}`}>
                <strong>Status:</strong> {testResult.status === 'success' ? 'Success' : 'Error'}
                <br />
                <strong>Message:</strong> {testResult.message}
              </div>

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
          {!testingServiceId && (
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
    </div>
  );
}

export default SandboxServicesPage;
