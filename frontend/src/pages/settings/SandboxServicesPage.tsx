import { useParams } from 'react-router-dom';
import { useState } from 'react';
import { Box, Plug, Pencil, ClipboardCopy, Trash2, Loader2, AlertTriangle } from 'lucide-react';
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
import { getProviderBadgeColor } from '../../components/ui/providerBadges';
import { AppRole } from '../../types/roles';

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
    <div className="p-6 text-center">
      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto"></div>
      <p className="mt-2 text-gray-600">Loading sandbox services...</p>
    </div>
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
        <div>
          <h2 className="text-xl font-semibold text-gray-900">Sandbox Services</h2>
          <p className="text-gray-600">Manage isolated code-execution environments used by the Code Interpreter capability</p>
        </div>
        {canEdit && (
          <div className="flex gap-2">
            <button
              onClick={handleCreate}
              className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg flex items-center"
            >
              <span className="mr-2">+</span>Add Sandbox Service
            </button>
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
              canEdit ? (
                <button type="button" className="text-sm font-medium text-gray-900 hover:text-blue-600 transition-colors text-left" onClick={() => handleEdit(service.service_id)}>
                  {service.name}
                </button>
              ) : (
                <span className="text-sm font-medium text-gray-900">{service.name}</span>
              )
            )
          },
          { header: 'Provider', render: (service: SandboxService) => (
            <span className={`inline-flex px-2 py-1 text-xs font-semibold rounded-full ${getProviderBadgeColor(service.provider)}`}>
              {service.provider}
            </span>
          )},
          { header: 'Status', render: (service: SandboxService) => (
            service.needs_api_key ? (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-yellow-100 text-yellow-800">
                <AlertTriangle className="w-3 h-3" /> API Key Required
              </span>
            ) : (
              <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
                Ready
              </span>
            )
          )},
          { header: 'Created', render: (service: any) => (service.created_at ? new Date(service.created_at).toLocaleDateString() : 'N/A') },
          { header: 'Actions', className: 'relative', render: (service: SandboxService) => (
            canEdit ? (
              <ActionDropdown actions={[
                {
                  label: testingServiceId === service.service_id ? 'Testing...' : 'Test Connection',
                  onClick: () => void handleTestConnection(service.service_id),
                  icon: testingServiceId === service.service_id ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plug className="w-4 h-4" />,
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
          <button onClick={handleCreate} className="bg-blue-600 hover:bg-blue-700 text-white px-6 py-3 rounded-lg">Add First Sandbox Service</button>
        </div>
      )}

      <div className="mt-6 bg-blue-50 border border-blue-200 rounded-lg p-4">
        <div className="flex">
          <div className="flex-shrink-0"><Box className="w-5 h-5 text-blue-400" /></div>
          <div className="ml-3">
            <h3 className="text-sm font-medium text-blue-800">About Sandbox Services</h3>
            <div className="mt-2 text-sm text-blue-700">
              <p>Sandbox Services configure the isolated environment where agents execute Python code when the Code Interpreter capability is enabled. Configure OpenSandbox (self-hosted container), Daytona, or E2B (managed cloud sandboxes).</p>
            </div>
          </div>
        </div>
      </div>

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
            <div className="text-center py-8">
              <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-blue-600 mx-auto mb-4"></div>
              <p className="text-gray-600">Testing connection to sandbox service...</p>
            </div>
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
