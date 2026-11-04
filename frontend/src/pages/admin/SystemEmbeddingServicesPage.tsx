import React, { useCallback, useEffect, useState } from 'react';
import { Users, Pencil, Trash2 } from 'lucide-react';
import { apiService } from '../../services/api';
import ServiceWizard from '../../components/services/wizard/ServiceWizard';
import CompactServiceEditor from '../../components/services/CompactServiceEditor';
import type { ServiceLifecycleFields, ServiceFormData } from '../../types/services';
import { LoadingState } from '../../components/ui/LoadingState';
import { ErrorState } from '../../components/ui/ErrorState';
import ActionDropdown from '../../components/ui/ActionDropdown';
import ServiceStatusBadge from '../../components/ui/ServiceStatusBadge';
import ServiceUsageModal from '../../components/services/ServiceUsageModal';
import { getServiceApiClient } from '../../components/services/serviceApi';
import { useServiceConnectionTest } from '../../components/services/useServiceConnectionTest';
import { SERVICE_USAGE_STRINGS } from '../../utils/serviceLifecycle';
import { useConfirm } from '../../contexts/ConfirmContext';
import { useSettingsCache } from '../../contexts/SettingsCacheContext';
import { useApiMutation } from '../../hooks/useApiMutation';
import { errorMessage, MESSAGES } from '../../constants/messages';

interface SystemEmbeddingService extends Partial<ServiceLifecycleFields> {
  readonly service_id: number;
  readonly name: string;
  readonly provider: string;
  readonly model_name: string;
  readonly api_key: string;
  readonly base_url: string;
  readonly api_version?: string;
  readonly aws_access_key_id?: string;
  readonly aws_region?: string;
  readonly is_system: boolean;
  readonly last_error?: string | null;
  readonly last_error_at?: string | null;
}

interface AffectedSilo {
  readonly silo_id: number;
  readonly silo_name: string;
  readonly app_id: number;
  readonly app_name: string;
}

interface DeletionImpact {
  readonly service_id: number;
  readonly service_name: string;
  readonly affected_silos_count: number;
  readonly affected_apps_count: number;
  readonly affected_silos: AffectedSilo[];
}

const SystemEmbeddingServicesPage: React.FC = () => {
  const confirm = useConfirm();
  const settingsCache = useSettingsCache();
  const mutate = useApiMutation();

  const [services, setServices] = useState<SystemEmbeddingService[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [usageService, setUsageService] = useState<{ id: number; name: string } | null>(null);
  const [editingService, setEditingService] = useState<SystemEmbeddingService | null>(null);
  const { testAction, modal: connectionTestModal } = useServiceConnectionTest('embedding');

  const fetchServices = useCallback(async () => {
    try {
      setIsLoading(true);
      setError(null);
      const data = (await apiService.getSystemEmbeddingServices()) as SystemEmbeddingService[];
      setServices(data);
    } catch (err) {
      setError(errorMessage(err, 'Failed to load services'));
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchServices();
  }, [fetchServices]);

  const handleOpenCreate = () => {
    setEditingService(null);
    setShowForm(true);
  };

  const handleOpenEdit = (svc: SystemEmbeddingService) => {
    setEditingService(svc);
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
          ? apiService.updateSystemEmbeddingService(editingService.service_id, data)
          : apiService.createSystemEmbeddingService(data),
      {
        loading: editingService
          ? MESSAGES.SAVING('embedding service')
          : MESSAGES.CREATING('embedding service'),
        success: editingService
          ? MESSAGES.UPDATED('embedding service')
          : MESSAGES.CREATED('embedding service'),
        error: (err) =>
          errorMessage(
            err,
            editingService
              ? MESSAGES.UPDATE_FAILED('embedding service')
              : MESSAGES.CREATE_FAILED('embedding service'),
          ),
      },
    );
    if (result === undefined) return;

    settingsCache.invalidateSystemServiceCaches();
    handleCancel();
    await fetchServices();
  };

  const testConnection = (serviceId: number) => {
    const service = services.find((item) => item.service_id === serviceId);
    if (!service) throw new Error('Embedding service not found');
    return getServiceApiClient('embedding', 'system', undefined).testConnection({
      name: service.name,
      provider: service.provider,
      model_name: service.model_name,
      api_key: service.api_key,
      base_url: service.base_url,
      api_version: service.api_version,
      aws_access_key_id: service.aws_access_key_id,
      aws_region: service.aws_region,
    }, serviceId);
  };

  const handleDelete = async (svc: SystemEmbeddingService) => {
    let impact: DeletionImpact | null = null;
    try {
      impact = (await apiService.getSystemEmbeddingServiceImpact(
        svc.service_id,
      )) as DeletionImpact;
    } catch (err) {
      const result = await confirm({
        title: MESSAGES.CONFIRM_DELETE_TITLE('embedding service'),
        message: (
          <>
            <p>{`Could not check deletion impact: ${errorMessage(err, 'unknown error')}.`}</p>
            <p className="mt-2">Delete this embedding service anyway?</p>
          </>
        ),
        variant: 'danger',
        confirmLabel: 'Delete',
      });
      if (!result) return;
      await runDelete(svc.service_id);
      return;
    }

    const ok = await confirm({
      title: MESSAGES.CONFIRM_DELETE_TITLE('embedding service'),
      message:
        impact.affected_silos_count > 0 ? (
          <div>
            <p>
              This embedding service is used by{' '}
              <span className="font-semibold">
                {impact.affected_silos_count} silo
                {impact.affected_silos_count !== 1 ? 's' : ''}
              </span>{' '}
              across{' '}
              <span className="font-semibold">
                {impact.affected_apps_count} app
                {impact.affected_apps_count !== 1 ? 's' : ''}
              </span>
              . Deleting it will leave those silos without an embedding service.
            </p>
            {impact.affected_silos.length < 20 && impact.affected_silos.length > 0 && (
              <ul className="mt-2 text-xs text-gray-500 list-disc list-inside space-y-0.5 max-h-40 overflow-y-auto">
                {impact.affected_silos.map((silo) => (
                  <li key={silo.silo_id}>
                    {silo.silo_name} ({silo.app_name})
                  </li>
                ))}
              </ul>
            )}
          </div>
        ) : (
          <p>Delete "{svc.name}"? This action cannot be undone.</p>
        ),
      variant: 'danger',
      confirmLabel: 'Delete',
    });
    if (!ok) return;
    await runDelete(svc.service_id);
  };

  const runDelete = async (serviceId: number) => {
    const result = await mutate(
      () => apiService.deleteSystemEmbeddingService(serviceId),
      {
        loading: MESSAGES.DELETING('embedding service'),
        success: MESSAGES.DELETED('embedding service'),
        error: (err) => errorMessage(err, MESSAGES.DELETE_FAILED('embedding service')),
      },
    );
    if (result === undefined) return;
    settingsCache.invalidateSystemServiceCaches();
    await fetchServices();
  };

  if (isLoading) return <LoadingState message="Loading system embedding services..." />;
  if (error) return <ErrorState error={error} onRetry={fetchServices} />;

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">System Embedding Services</h1>
          <p className="text-gray-600">
            Shared embedding provider configurations available to every app.
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
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Status
              </th>
              <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                Actions
              </th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {services.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-6 py-8 text-center text-sm text-gray-500">
                  No system embedding services configured.
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
                  <td className="px-6 py-4 text-sm">
                    <ServiceStatusBadge lastError={svc.last_error} lastErrorAt={svc.last_error_at} lifecycleStatus={svc.lifecycle_status} endOfServiceAt={svc.end_of_service_at} deprecationNotice={svc.deprecation_notice} />
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-right">
                    <div className="inline-flex justify-end">
                      <ActionDropdown
                        size="sm"
                        triggerAriaLabel={`Actions for ${svc.name}`}
                        actions={[
                          {
                            label: SERVICE_USAGE_STRINGS.action,
                            icon: <Users className="w-4 h-4" />,
                            onClick: () => setUsageService({ id: svc.service_id, name: svc.name }),
                          },
                          testAction(svc.service_id, svc.name, () => testConnection(svc.service_id)),
                          {
                            label: 'Edit',
                            icon: <Pencil className="w-4 h-4" />,
                            onClick: () => handleOpenEdit(svc),
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
          kind="embedding"
          scope="system"
          existingNames={services.map((s) => s.name)}
          onClose={handleCancel}
          onSave={handleSave}
        />
      )}

      {showForm && editingService && (
        <CompactServiceEditor
          isOpen
          kind="embedding"
          scope="system"
          service={editingService}
          existingNames={services.map((s) => s.name)}
          onClose={handleCancel}
          onSave={handleSave}
        />
      )}

      {usageService && (
        <ServiceUsageModal
          kind="embedding"
          scope="system"
          serviceId={usageService.id}
          serviceName={usageService.name}
          onClose={() => setUsageService(null)}
        />
      )}
      {connectionTestModal}
    </div>
  );
};

export default SystemEmbeddingServicesPage;
