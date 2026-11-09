import React, { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Users, Pencil, Trash2, Cpu } from 'lucide-react';
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
import { errorMessage } from '../../constants/messages';
import Title from '../../components/ui/Title';
import ButtonApp from '../../components/ui/ButtonApp';
import Table, { type TableColumn } from '../../components/ui/Table';
import BackgroundImage from '../../components/ui/BackgroundImage';
import SidePanel from '../../components/ui/SidePanel';

interface SystemAIService extends Partial<ServiceLifecycleFields> {
  readonly service_id: number;
  readonly name: string;
  readonly provider: string;
  readonly model_name: string;
  readonly api_key: string;
  readonly base_url: string;
  readonly is_system: boolean;
  readonly last_error?: string | null;
  readonly last_error_at?: string | null;
  readonly supports_video: boolean;
  readonly created_at: string;
  readonly available_providers: { value: string; name: string }[];
}

const SystemAIServicesPage: React.FC = () => {
  const { t } = useTranslation('common');
  const confirm = useConfirm();
  const settingsCache = useSettingsCache();
  const mutate = useApiMutation();

  const [services, setServices] = useState<SystemAIService[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [usageService, setUsageService] = useState<{ id: number; name: string } | null>(null);
  const [editingService, setEditingService] = useState<SystemAIService | null>(null);
  const { testAction, modal: connectionTestModal } = useServiceConnectionTest('AI');

  const fetchServices = useCallback(async () => {
    try {
      setIsLoading(true);
      setError(null);
      const data = (await apiService.getSystemAIServices()) as SystemAIService[];
      setServices(data);
    } catch (err) {
      setError(errorMessage(err, t('systemAiServicesPage.loadFailed')));
    } finally {
      setIsLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void fetchServices();
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
          ? t('systemAiServicesPage.updating')
          : t('systemAiServicesPage.creating'),
        success: editingService
          ? t('systemAiServicesPage.updated')
          : t('systemAiServicesPage.created'),
        error: (err) => errorMessage(
          err,
          editingService
            ? t('systemAiServicesPage.updateFailed')
            : t('systemAiServicesPage.createFailed'),
        ),
      },
    );
    if (result === undefined) return;

    settingsCache.invalidateSystemServiceCaches();
    handleCancel();
    await fetchServices();
  };

  const testConnection = async (serviceId: number) => {
    const detail = await apiService.getSystemAIService(serviceId);
    return getServiceApiClient('ai', 'system', undefined).testConnection({
      name: detail.name,
      provider: detail.provider,
      model_name: detail.model_name,
      api_key: detail.api_key,
      base_url: detail.base_url,
      api_version: detail.api_version,
      supports_video: detail.supports_video,
      aws_access_key_id: detail.aws_access_key_id,
      aws_region: detail.aws_region,
    }, serviceId);
  };

  const handleDelete = async (service: SystemAIService) => {
    const ok = await confirm({
      title: t('systemAiServicesPage.deleteTitle'),
      message: t('systemAiServicesPage.deleteMessage', { name: service.name }),
      variant: 'danger',
      confirmLabel: t('aiServicesPage.actions.delete'),
    });
    if (!ok) return;

    const result = await mutate(
      () => apiService.deleteSystemAIService(service.service_id),
      {
        loading: t('systemAiServicesPage.deleting'),
        success: t('systemAiServicesPage.deleted'),
        error: (err) => errorMessage(err, t('systemAiServicesPage.deleteFailed')),
      },
    );
    if (result === undefined) return;
    settingsCache.invalidateSystemServiceCaches();
    await fetchServices();
  };

  const columns: TableColumn<SystemAIService>[] = [
    {
      header: t('aiServicesPage.columns.name'),
      className: 'px-6 py-4 whitespace-nowrap',
      render: (svc) => (
        <div className="flex items-center gap-2">
          <BackgroundImage icon={Cpu} variant="marron" />
          <button
            type="button"
            onClick={() => void handleOpenEdit(svc)}
            className="text-left text-sm font-medium text-fg dark:text-fg-dark"
          >
            {svc.name}
          </button>
        </div>
      ),
    },
    {
      header: t('aiServicesPage.columns.provider'),
      accessor: 'provider',
      className: 'px-6 py-4 whitespace-nowrap text-xs text-fg-secondary dark:text-fg-secondary-dark',
    },
    {
      header: t('aiServicesPage.columns.model'),
      accessor: 'model_name',
      className: 'px-6 py-4 whitespace-nowrap text-xs text-fg-secondary dark:text-fg-secondary-dark',
    },
    {
      header: t('aiServicesPage.columns.status'),
      className: 'px-6 py-4 text-sm',
      render: (svc) => (
        <ServiceStatusBadge
          lastError={svc.last_error}
          lastErrorAt={svc.last_error_at}
          lifecycleStatus={svc.lifecycle_status}
          endOfServiceAt={svc.end_of_service_at}
          deprecationNotice={svc.deprecation_notice}
        />
      ),
    },
    {
      header: t('aiServicesPage.columns.actions'),
      sticky: 'right' as const,
      headerClassName: 'text-right',
      className: 'px-6 py-4 whitespace-nowrap text-right',
      render: (svc) => (
        <div className="inline-flex justify-end">
          <ActionDropdown
            size="sm"
            triggerAriaLabel={t('aiServicesPage.actions.menuForService', { name: svc.name })}
            actions={[
              {
                label: SERVICE_USAGE_STRINGS.action,
                icon: <Users className="w-4 h-4" />,
                onClick: () => setUsageService({ id: svc.service_id, name: svc.name }),
              },
              testAction(svc.service_id, svc.name, () => testConnection(svc.service_id)),
              {
                label: t('aiServicesPage.actions.edit'),
                icon: <Pencil className="w-4 h-4" />,
                onClick: () => {
                  void handleOpenEdit(svc);
                },
              },
              {
                label: t('aiServicesPage.actions.delete'),
                icon: <Trash2 className="w-4 h-4" />,
                variant: 'danger',
                onClick: () => {
                  void handleDelete(svc);
                },
              },
            ]}
          />
        </div>
      ),
    },
  ];

  if (isLoading) return(
    <div className="space-y-6">
                {/* Page Header */}
                <div className="flex items-center justify-between">
                  <Title variant='titPrincipal' titulo={t('systemAiServicesPage.title')} subtitulo={t('systemAiServicesPage.subtitle')}></Title>
                </div>
                <LoadingState variant="page" message={t('systemAiServicesPage.loading')} />
              </div>
  );
  if (error) return <ErrorState error={error} onRetry={fetchServices} />;

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <Title variant='titPrincipal' titulo={t('systemAiServicesPage.title')} subtitulo={t('systemAiServicesPage.subtitle')}></Title>
        <ButtonApp
          label={t('aiServicesPage.addService')}
          onClick={handleOpenCreate}
          variant="primary"
          size="medium"
        />
      </div>

      <Table
        columns={columns}
        stickyEdgeColumns
        data={services}
        keyExtractor={(svc) => svc.service_id}
        emptyIcon={<BackgroundImage icon={Cpu} size={64} iconSize={32} />}
        emptyMessage={t('systemAiServicesPage.empty')}
      />

      {services.length === 0 && (
        <div className="text-center py-6">
          <ButtonApp
            label={t('aiServicesPage.addFirstService')}
            onClick={handleOpenCreate}
            variant="primary"
            size="medium"
          />
        </div>
      )}

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
          variant="panel"
          kind="ai"
          scope="system"
          service={editingService}
          existingNames={services.map((s) => s.name)}
          onClose={handleCancel}
          onSave={handleSave}
        />
      )}

      {/* Service usage side panel — fixed wrapper that starts below the 56px (h-14) app header */}
      {usageService && (
        <div className="fixed inset-x-0 bottom-0 top-14 z-30 !mt-0">
          <SidePanel
            open
            side="right"
            onClose={() => setUsageService(null)}
            title={t('systemAiServicesPage.title')}
            headerActions={(
              <span className="rounded-full bg-surface-hover px-2 py-0.5 text-[11px] normal-case tracking-normal text-fg-secondary dark:bg-surface-hover-dark dark:text-fg-secondary-dark">
                {SERVICE_USAGE_STRINGS.action}
              </span>
            )}
            widthClassName="w-[640px] max-w-full"
          >
            <ServiceUsageModal
              key={usageService.id}
              kind="ai"
              scope="system"
              variant="panel"
              serviceId={usageService.id}
              serviceName={usageService.name}
              onClose={() => setUsageService(null)}
            />
          </SidePanel>
        </div>
      )}
      {connectionTestModal}
    </div>
  );
};

export default SystemAIServicesPage;
