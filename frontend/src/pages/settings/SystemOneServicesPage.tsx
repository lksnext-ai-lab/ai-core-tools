import { useParams } from 'react-router-dom';
import { useState } from 'react';
import { Pencil, ClipboardCopy, Trash2, Loader2, Plug, Gauge, AlertTriangle } from 'lucide-react';
import Modal from '../../components/ui/Modal';
import ActionDropdown from '../../components/ui/ActionDropdown';
import SystemOneServiceWizard from '../../components/services/SystemOneServiceWizard';
import { useAppRole } from '../../hooks/useAppRole';
import ReadOnlyBanner from '../../components/ui/ReadOnlyBanner';
import Alert from '../../components/ui/Alert';
import Table from '../../components/ui/Table';
import { useServicesManager } from '../../hooks/useServicesManager';
import { apiService } from '../../services/api';
import { AppRole } from '../../types/roles';
import type {
  SystemOneConnectionResult,
  SystemOneService,
  SystemOneServicePayload,
} from '../../types/systemOne';

// The agent form reads its own list from the agent detail, so this page needs no shared settings cache.
const noCache = {
  get: () => null,
  set: () => undefined,
  invalidate: () => undefined,
};

function SystemOneServicesPage() {
  const { appId } = useParams();
  const { hasMinRole, userRole } = useAppRole(appId);
  const canEdit = hasMinRole(AppRole.ADMINISTRATOR);

  const api = {
    getAll: (id: number) => apiService.getSystemOneServices(id),
    getOne: (id: number, sid: number) => apiService.getSystemOneService(id, sid),
    create: (id: number, data: SystemOneServicePayload) => apiService.createSystemOneService(id, data),
    update: (id: number, sid: number, data: SystemOneServicePayload) => apiService.updateSystemOneService(id, sid, data),
    delete: (id: number, sid: number) => apiService.deleteSystemOneService(id, sid),
    copy: (id: number, sid: number) => apiService.copySystemOneService(id, sid),
  };

  const {
    services, loading, error, isModalOpen, editingService,
    handleClose, handleCreate, handleDelete, handleEdit, handleCopy, handleSave,
    setIsModalOpen, setEditingService,
  } = useServicesManager<SystemOneService>(appId, api, noCache, {
    entity: 'System One service',
    deleteWarning: (service: SystemOneService) => {
      const n = service?.agent_count ?? 0;
      return n > 0
        ? `${n} agent${n === 1 ? '' : 's'} use${n === 1 ? 's' : ''} this service and will stop working until you assign ${n === 1 ? 'it' : 'them'} another one.`
        : null;
    },
  });

  const [testResult, setTestResult] = useState<SystemOneConnectionResult | null>(null);
  const [isTestModalOpen, setIsTestModalOpen] = useState(false);
  const [testingServiceId, setTestingServiceId] = useState<number | null>(null);

  async function handleTestConnection(serviceId: number) {
    if (!appId) return;
    setTestingServiceId(serviceId);
    setTestResult(null);
    setIsTestModalOpen(true);
    try {
      setTestResult(await apiService.testSystemOneService(Number.parseInt(appId), serviceId));
    } catch (err) {
      setTestResult({
        status: 'error',
        message: err instanceof Error ? err.message : 'Failed to test the connection',
        models: [],
        limits: null,
      });
    } finally {
      setTestingServiceId(null);
    }
  }

  if (loading) return (
    <div className="p-6 text-center">
      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto"></div>
      <p className="mt-2 text-gray-600">Loading System One services...</p>
    </div>
  );

  if (error) return (
    <div className="p-6">
      <Alert type="error" message={error} onDismiss={() => { setIsModalOpen(false); setEditingService(null); }} />
    </div>
  );

  return (
    <div className="p-6">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h2 className="text-xl font-semibold text-gray-900">System One Services</h2>
          <p className="text-gray-600">Connections to System One servers used by System One agents</p>
        </div>
        {canEdit && (
          <button onClick={handleCreate} className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg flex items-center">
            <span className="mr-2">+</span>Add System One Service
          </button>
        )}
      </div>

      {!canEdit && <ReadOnlyBanner userRole={userRole} minRole={AppRole.ADMINISTRATOR} />}

      <Table
        data={services}
        keyExtractor={(service) => service.service_id.toString()}
        columns={[
          {
            header: 'Name',
            render: (service: SystemOneService) => (
              canEdit ? (
                <button type="button" className="text-sm font-medium text-gray-900 hover:text-blue-600 transition-colors text-left" onClick={() => void handleEdit(service.service_id)}>
                  {service.name}
                </button>
              ) : (
                <span className="text-sm font-medium text-gray-900">{service.name}</span>
              )
            ),
          },
          { header: 'Server', render: (service: SystemOneService) => <span className="text-sm text-gray-700">{service.endpoint}</span> },
          { header: 'Model', render: (service: SystemOneService) => <span className="text-sm text-gray-700">{service.model}</span> },
          { header: 'Status', render: (service: SystemOneService) => (
            service.model ? (
              <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">Ready</span>
            ) : (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-yellow-100 text-yellow-800">
                <AlertTriangle className="w-3 h-3" /> Model required
              </span>
            )
          )},
          { header: 'Agents', render: (service: SystemOneService) => <span className="text-sm text-gray-700">{service.agent_count ?? 0}</span> },
          { header: 'Concurrency', render: (service: SystemOneService) => <span className="text-sm text-gray-700">{service.max_concurrency}</span> },
          { header: 'Created', render: (service: SystemOneService) => (service.created_at ? new Date(service.created_at).toLocaleDateString() : 'N/A') },
          {
            header: 'Actions',
            className: 'relative',
            render: (service: SystemOneService) => (
              canEdit ? (
                <ActionDropdown actions={[
                  {
                    label: testingServiceId === service.service_id ? 'Testing...' : 'Test Connection',
                    onClick: () => void handleTestConnection(service.service_id),
                    icon: testingServiceId === service.service_id ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plug className="w-4 h-4" />,
                    disabled: testingServiceId === service.service_id,
                  },
                  { label: 'Edit', onClick: () => void handleEdit(service.service_id), icon: <Pencil className="w-4 h-4" />, variant: 'primary' as const },
                  { label: 'Copy', onClick: () => void handleCopy(service.service_id), icon: <ClipboardCopy className="w-4 h-4" />, variant: 'primary' as const },
                  { label: 'Delete', onClick: () => void handleDelete(service.service_id), icon: <Trash2 className="w-4 h-4" />, variant: 'danger' as const },
                ]} size="sm" />
              ) : (
                <span className="text-gray-400 text-sm">View only</span>
              )
            ),
          },
        ]}
        emptyIcon={<Gauge className="w-10 h-10 text-gray-300" />}
        emptyMessage="No System One Services"
        emptySubMessage="Add a System One service to create agents that classify, judge or decide over a text."
        loading={loading}
      />

      {!loading && services.length === 0 && canEdit && (
        <div className="text-center py-6">
          <button onClick={handleCreate} className="bg-blue-600 hover:bg-blue-700 text-white px-6 py-3 rounded-lg">Add First System One Service</button>
        </div>
      )}

      <div className="mt-6 bg-blue-50 border border-blue-200 rounded-lg p-4">
        <div className="flex">
          <div className="flex-shrink-0"><Gauge className="w-5 h-5 text-blue-400" /></div>
          <div className="ml-3">
            <h3 className="text-sm font-medium text-blue-800">About System One</h3>
            <p className="mt-2 text-sm text-blue-700">
              System One answers closed questions about a text (yes/no, pick a category, score on a scale) with probabilities, without
              generating text. In this version it evaluates text only: images are not supported. Deleting a service does not delete its
              agents: they stay, but cannot run until you assign them another service.
            </p>
          </div>
        </div>
      </div>

      {isModalOpen && appId && (
        <SystemOneServiceWizard
          key={editingService?.service_id ?? 'new'}
          isOpen
          appId={Number.parseInt(appId)}
          service={editingService}
          existingNames={services.map((s) => s.name)}
          onClose={handleClose}
          onSave={handleSave}
        />
      )}

      <Modal isOpen={isTestModalOpen} onClose={() => !testingServiceId && setIsTestModalOpen(false)} title="Connection Test Result">
        <div className="p-4">
          {testingServiceId ? (
            <div className="text-center py-8">
              <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-blue-600 mx-auto mb-4"></div>
              <p className="text-gray-600">Testing connection to the System One server...</p>
            </div>
          ) : testResult && (
            <div>
              <div className={`mb-4 p-3 rounded ${testResult.status === 'success' ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'}`}>
                <strong>Status:</strong> {testResult.status === 'success' ? 'Success' : 'Error'}
                <br />
                <strong>Message:</strong> {testResult.message}
              </div>
              {testResult.models.length > 0 && (
                <p className="text-sm text-gray-700 mb-2"><strong>Models:</strong> {testResult.models.join(', ')}</p>
              )}
              {testResult.limits && (
                <div className="bg-gray-50 p-3 rounded border text-sm font-mono whitespace-pre-wrap">
                  {Object.entries(testResult.limits).map(([k, v]) => `${k}: ${v}`).join('\n')}
                </div>
              )}
            </div>
          )}
          {!testingServiceId && (
            <div className="mt-4 flex justify-end">
              <button onClick={() => setIsTestModalOpen(false)} className="bg-gray-200 hover:bg-gray-300 text-gray-800 px-4 py-2 rounded">Close</button>
            </div>
          )}
        </div>
      </Modal>
    </div>
  );
}

export default SystemOneServicesPage;
