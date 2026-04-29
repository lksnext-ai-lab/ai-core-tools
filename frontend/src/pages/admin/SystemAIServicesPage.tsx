import React, { useCallback, useEffect, useState } from 'react';
import { Pencil, Trash2 } from 'lucide-react';
import { apiService } from '../../services/api';
import ServiceWizard from '../../components/services/wizard/ServiceWizard';
import CompactServiceEditor from '../../components/services/CompactServiceEditor';
import type { ServiceFormData } from '../../types/services';
import { LoadingState } from '../../components/ui/LoadingState';
import { ErrorState } from '../../components/ui/ErrorState';
import ActionDropdown from '../../components/ui/ActionDropdown';
import { useConfirm } from '../../contexts/ConfirmContext';
import { useApiMutation } from '../../hooks/useApiMutation';
import { errorMessage, MESSAGES } from '../../constants/messages';

interface SystemAIService {
  readonly service_id: number;
  readonly name: string;
  readonly provider: string;
  readonly model_name: string;
  readonly api_key: string;
  readonly base_url: string;
  readonly is_system: boolean;
  readonly supports_video: boolean;
  readonly created_at: string;
  readonly available_providers: { value: string; name: string }[];
}

const SystemAIServicesPage: React.FC = () => {
  const confirm = useConfirm();
  const mutate = useApiMutation();

  const [services, setServices] = useState<SystemAIService[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [editingService, setEditingService] = useState<SystemAIService | null>(null);

  const fetchServices = useCallback(async () => {
    try {
      setIsLoading(true);
      setError(null);
      const data = (await apiService.getSystemAIServices()) as SystemAIService[];
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

  const handleOpenEdit = async (svc: SystemAIService) => {
    try {
      const detail = (await apiService.getSystemAIService(svc.service_id)) as SystemAIService;
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

  const handleSave = async (data: ServiceFormData) => {
    const result = await mutate(
      () =>
        editingService
          ? apiService.updateSystemAIService(editingService.service_id, data)
          : apiService.createSystemAIService(data),
      {
        loading: editingService
          ? MESSAGES.SAVING('AI service')
          : MESSAGES.CREATING('AI service'),
        success: editingService
          ? MESSAGES.UPDATED('AI service')
          : MESSAGES.CREATED('AI service'),
        error: (err) =>
          errorMessage(
            err,
            editingService
              ? MESSAGES.UPDATE_FAILED('AI service')
              : MESSAGES.CREATE_FAILED('AI service'),
          ),
      },
    );
    if (result === undefined) return;

    handleCancel();
    await fetchServices();
  };

  const handleDelete = async (service: SystemAIService) => {
    const ok = await confirm({
      title: MESSAGES.CONFIRM_DELETE_TITLE('system AI service'),
      message: `Delete "${service.name}"? Agents using this service will need to be reassigned.`,
      variant: 'danger',
      confirmLabel: 'Delete',
    });
    if (!ok) return;

    const result = await mutate(
      () => apiService.deleteSystemAIService(service.service_id),
      {
        loading: MESSAGES.DELETING('AI service'),
        success: MESSAGES.DELETED('AI service'),
        error: (err) => errorMessage(err, MESSAGES.DELETE_FAILED('AI service')),
      },
    );
    if (result === undefined) return;
    await fetchServices();
  };

  if (isLoading) return <LoadingState message="Loading system AI services..." />;
  if (error) return <ErrorState error={error} onRetry={fetchServices} />;

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">System AI Services</h1>
          <p className="text-gray-600">
            Shared LLM provider configurations available to every app.
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
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Model
              </th>
              <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                Actions
              </th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {services.length === 0 ? (
              <tr>
                <td colSpan={4} className="px-6 py-8 text-center text-sm text-gray-500">
                  No system AI services configured.
                </td>
              </tr>
            ) : (
              services.map((svc) => (
                <tr key={svc.service_id} className="hover:bg-gray-50">
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">{svc.name}</td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-700">
                    {svc.provider}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-700">
                    {svc.model_name}
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
          kind="ai"
          scope="system"
          existingNames={services.map((s) => s.name)}
          onClose={handleCancel}
          onSave={handleSave}
        />
      )}

      {showForm && editingService && (
        <CompactServiceEditor
          isOpen
          kind="ai"
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

export default SystemAIServicesPage;
