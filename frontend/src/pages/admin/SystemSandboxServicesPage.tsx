import React, { useCallback, useEffect, useState } from 'react';
import { Pencil, Trash2 } from 'lucide-react';
import { apiService } from '../../services/api';
import ServiceWizard from '../../components/services/wizard/ServiceWizard';
import CompactServiceEditor from '../../components/services/CompactServiceEditor';
import type { SandboxServiceFormData } from '../../types/services';
import { LoadingState } from '../../components/ui/LoadingState';
import { ErrorState } from '../../components/ui/ErrorState';
import ActionDropdown from '../../components/ui/ActionDropdown';
import { useConfirm } from '../../contexts/ConfirmContext';
import { useApiMutation } from '../../hooks/useApiMutation';
import { errorMessage, MESSAGES } from '../../constants/messages';

interface SystemSandboxService {
  readonly service_id: number;
  readonly name: string;
  readonly provider: string;
  readonly api_key: string;
  readonly base_url: string;
  readonly is_system: boolean;
  readonly created_at: string;
}

const SystemSandboxServicesPage: React.FC = () => {
  const confirm = useConfirm();
  const mutate = useApiMutation();

  const [services, setServices] = useState<SystemSandboxService[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [editingService, setEditingService] = useState<SystemSandboxService | null>(null);

  const fetchServices = useCallback(async () => {
    try {
      setIsLoading(true);
      setError(null);
      const data = (await apiService.getSystemSandboxServices()) as SystemSandboxService[];
      setServices(data);
    } catch (err) {
      setError(errorMessage(err, 'Failed to load services'));
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchServices();
  }, [fetchServices]);

  const handleOpenCreate = () => {
    setEditingService(null);
    setShowForm(true);
  };

  const handleOpenEdit = async (svc: SystemSandboxService) => {
    try {
      const detail = (await apiService.getSystemSandboxService(svc.service_id)) as SystemSandboxService;
      setEditingService(detail);
    } catch {
      setEditingService(svc);
    }
    setShowForm(true);
  };

  const handleCancel = () => {
    setShowForm(false);
    setEditingService(null);
  };

  const handleSave = async (data: SandboxServiceFormData) => {
    const result = await mutate(
      () =>
        editingService
          ? apiService.updateSystemSandboxService(editingService.service_id, data)
          : apiService.createSystemSandboxService(data),
      {
        loading: editingService
          ? MESSAGES.SAVING('sandbox service')
          : MESSAGES.CREATING('sandbox service'),
        success: editingService
          ? MESSAGES.UPDATED('sandbox service')
          : MESSAGES.CREATED('sandbox service'),
        error: (err) =>
          errorMessage(
            err,
            editingService
              ? MESSAGES.UPDATE_FAILED('sandbox service')
              : MESSAGES.CREATE_FAILED('sandbox service'),
          ),
      },
    );
    if (result === undefined) return;

    handleCancel();
    await fetchServices();
  };

  const handleDelete = async (service: SystemSandboxService) => {
    const ok = await confirm({
      title: MESSAGES.CONFIRM_DELETE_TITLE('system sandbox service'),
      message: `Delete "${service.name}"? Agents using this service will need to be reassigned.`,
      variant: 'danger',
      confirmLabel: 'Delete',
    });
    if (!ok) return;

    const result = await mutate(
      () => apiService.deleteSystemSandboxService(service.service_id),
      {
        loading: MESSAGES.DELETING('sandbox service'),
        success: MESSAGES.DELETED('sandbox service'),
        error: (err) => errorMessage(err, MESSAGES.DELETE_FAILED('sandbox service')),
      },
    );
    if (result === undefined) return;
    await fetchServices();
  };

  if (isLoading) return <LoadingState message="Loading system sandbox services..." />;
  if (error) return <ErrorState error={error} onRetry={fetchServices} />;

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">System Sandbox Services</h1>
          <p className="text-gray-600">
            Shared code-execution sandbox configurations available to every app.
          </p>
        </div>
        <button
          type="button"
          onClick={handleOpenCreate}
          className="bg-blue-600 text-white rounded-lg px-4 py-2 text-sm font-medium hover:bg-blue-700"
        >
          Add service
        </button>
      </div>

      <div className="bg-white shadow rounded-lg overflow-x-auto overflow-visible">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Name
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Provider
              </th>
              <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                Actions
              </th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {services.length === 0 ? (
              <tr>
                <td colSpan={3} className="px-6 py-8 text-center text-sm text-gray-500">
                  No system sandbox services configured.
                </td>
              </tr>
            ) : (
              services.map((svc) => (
                <tr key={svc.service_id} className="hover:bg-gray-50">
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">{svc.name}</td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-700">
                    {svc.provider}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-right">
                    <div className="inline-flex justify-end">
                      <ActionDropdown
                        size="sm"
                        actions={[
                          {
                            label: 'Edit',
                            icon: <Pencil className="w-4 h-4" />,
                            onClick: () => {
                              void handleOpenEdit(svc);
                            },
                          },
                          {
                            label: 'Delete',
                            icon: <Trash2 className="w-4 h-4" />,
                            variant: 'danger',
                            onClick: () => {
                              void handleDelete(svc);
                            },
                          },
                        ]}
                      />
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {showForm && !editingService && (
        <ServiceWizard
          isOpen
          kind="sandbox"
          scope="system"
          existingNames={services.map((s) => s.name)}
          onClose={handleCancel}
          onSave={handleSave}
        />
      )}

      {showForm && editingService && (
        <CompactServiceEditor
          isOpen
          kind="sandbox"
          scope="system"
          service={editingService}
          existingNames={services.map((s) => s.name)}
          onClose={handleCancel}
          onSave={handleSave}
        />
      )}
    </div>
  );
};

export default SystemSandboxServicesPage;
