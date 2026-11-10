import React, { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Pencil, Trash2, Users, Box } from 'lucide-react';
import { apiService } from '../../services/api';
import ServiceWizard from '../../components/services/wizard/ServiceWizard';
import CompactServiceEditor from '../../components/services/CompactServiceEditor';
import type { SandboxServiceFormData, ServiceLifecycleFields } from '../../types/services';
import ServiceStatusBadge from '../../components/ui/ServiceStatusBadge';
import ServiceUsageModal from '../../components/services/ServiceUsageModal';
import { getServiceApiClient } from '../../components/services/serviceApi';
import { useServiceConnectionTest } from '../../components/services/useServiceConnectionTest';
import { SERVICE_USAGE_STRINGS } from '../../utils/serviceLifecycle';
import { LoadingState } from '../../components/ui/LoadingState';
import { ErrorState } from '../../components/ui/ErrorState';
import ActionDropdown from '../../components/ui/ActionDropdown';
import { useConfirm } from '../../contexts/ConfirmContext';
import { useSettingsCache } from '../../contexts/SettingsCacheContext';
import { useApiMutation } from '../../hooks/useApiMutation';
import { errorMessage } from '../../constants/messages';
import Title from '../../components/ui/Title';
import ButtonApp from '../../components/ui/ButtonApp';
import Table, { type TableColumn } from '../../components/ui/Table';
import BackgroundImage from '../../components/ui/BackgroundImage';
import SidePanel from '../../components/ui/SidePanel';

interface SystemSandboxService extends Partial<ServiceLifecycleFields> {
  readonly service_id: number;
  readonly name: string;
  readonly provider: string;
  readonly api_key: string;
  readonly base_url: string;
  readonly is_system: boolean;
  readonly needs_api_key?: boolean;
  readonly created_at: string;
}

const SystemSandboxServicesPage: React.FC = () => {
  const { t } = useTranslation('common');
  const confirm = useConfirm();
  const settingsCache = useSettingsCache();
  const mutate = useApiMutation();

  const [services, setServices] = useState<SystemSandboxService[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [usageService, setUsageService] = useState<{ id: number; name: string } | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [editingService, setEditingService] = useState<SystemSandboxService | null>(null);
  const { testAction, modal: connectionTestModal } = useServiceConnectionTest('sandbox');

  const fetchServices = useCallback(async () => {
    try {
      setIsLoading(true);
      setError(null);
      const data = (await apiService.getSystemSandboxServices()) as SystemSandboxService[];
      setServices(data);
    } catch (err) {
      setError(errorMessage(err, t('systemSandboxServicesPage.loadFailed')));
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
          ? t('systemSandboxServicesPage.updating')
          : t('systemSandboxServicesPage.creating'),
        success: editingService
          ? t('systemSandboxServicesPage.updated')
          : t('systemSandboxServicesPage.created'),
        error: (err) => errorMessage(
          err,
          editingService
            ? t('systemSandboxServicesPage.updateFailed')
            : t('systemSandboxServicesPage.createFailed'),
        ),
      },
    );
    if (result === undefined) return;

    settingsCache.invalidateSystemServiceCaches();
    handleCancel();
    await fetchServices();
  };

  const testConnection = async (serviceId: number) => {
    const detail = await apiService.getSystemSandboxService(serviceId);
    return getServiceApiClient('sandbox', 'system', undefined).testConnection({
      name: detail.name,
      provider: detail.provider,
      api_key: detail.api_key,
      base_url: detail.base_url,
      opensandbox_image: detail.opensandbox_image,
      daytona_target: detail.daytona_target,
      daytona_workspace: detail.daytona_workspace,
      daytona_cpu: detail.daytona_cpu,
      daytona_memory_gb: detail.daytona_memory_gb,
      e2b_template: detail.e2b_template,
      e2b_workspace: detail.e2b_workspace,
    }, serviceId);
  };

  const handleDelete = async (service: SystemSandboxService) => {
    const ok = await confirm({
      title: t('systemSandboxServicesPage.deleteTitle'),
      message: t('systemSandboxServicesPage.deleteMessage', { name: service.name }),
      variant: 'danger',
      confirmLabel: t('sandboxServicesPage.actions.delete'),
    });
    if (!ok) return;

    const result = await mutate(
      () => apiService.deleteSystemSandboxService(service.service_id),
      {
        loading: t('systemSandboxServicesPage.deleting'),
        success: t('systemSandboxServicesPage.deleted'),
        error: (err) => errorMessage(err, t('systemSandboxServicesPage.deleteFailed')),
      },
    );
    if (result === undefined) return;
    settingsCache.invalidateSystemServiceCaches();
    await fetchServices();
  };

  const columns: TableColumn<SystemSandboxService>[] = [
    {
      header: t('sandboxServicesPage.columns.name'),
      className: 'px-6 py-4 whitespace-nowrap',
      render: (svc) => (
        <div className="flex items-center gap-2">
          <BackgroundImage icon={Box} variant="marron" size={34} iconSize={17} />
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
      header: t('sandboxServicesPage.columns.provider'),
      accessor: 'provider',
      className: 'px-6 py-4 whitespace-nowrap text-xs text-fg-secondary dark:text-fg-secondary-dark',
    },
    {
      header: t('sandboxServicesPage.columns.status'),
      className: 'px-6 py-4 text-sm',
      render: (svc) => (
        <ServiceStatusBadge
          needsApiKey={svc.needs_api_key}
          lifecycleStatus={svc.lifecycle_status}
          endOfServiceAt={svc.end_of_service_at}
          deprecationNotice={svc.deprecation_notice}
        />
      ),
    },
    {
      header: t('sandboxServicesPage.columns.actions'),
      sticky: 'right' as const,
      headerClassName: 'text-right',
      className: 'px-6 py-4 whitespace-nowrap text-right',
      render: (svc) => (
        <div className="inline-flex justify-end">
          <ActionDropdown
            size="sm"
            triggerAriaLabel={t('sandboxServicesPage.actions.menuForService', { name: svc.name })}
            actions={[
              {
                label: SERVICE_USAGE_STRINGS.action,
                icon: <Users className="w-4 h-4" />,
                onClick: () => setUsageService({ id: svc.service_id, name: svc.name }),
              },
              testAction(svc.service_id, svc.name, () => testConnection(svc.service_id)),
              {
                label: t('sandboxServicesPage.actions.edit'),
                icon: <Pencil className="w-4 h-4" />,
                onClick: () => {
                  void handleOpenEdit(svc);
                },
              },
              {
                label: t('sandboxServicesPage.actions.delete'),
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
        <div className="flex items-center justify-between">
          <Title variant='titPrincipal' titulo={t('systemSandboxServicesPage.title')} subtitulo={t('systemSandboxServicesPage.subtitle')}></Title>
        </div>
        <LoadingState message={t('systemSandboxServicesPage.loading')} />
      </div>
    );
  if (error) return <ErrorState error={error} onRetry={fetchServices} />;

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <Title variant='titPrincipal' titulo={t('systemSandboxServicesPage.title')} subtitulo={t('systemSandboxServicesPage.subtitle')}></Title>
        <ButtonApp
            label={t('sandboxServicesPage.addService')}
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
        emptyIcon={<BackgroundImage icon={Box} size={64} iconSize={32} />}
        emptyMessage={t('systemSandboxServicesPage.empty')}
      />

      {services.length === 0 && (
        <div className="text-center py-6">
          <ButtonApp
            label={t('sandboxServicesPage.addFirstService')}
            onClick={handleOpenCreate}
            variant="primary"
            size="medium"
          />
        </div>
      )}

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
          variant="panel"
          kind="sandbox"
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
            title={t('systemSandboxServicesPage.title')}
            headerActions={(
              <span className="rounded-full bg-surface-hover px-2 py-0.5 text-[11px] normal-case tracking-normal text-fg-secondary dark:bg-surface-hover-dark dark:text-fg-secondary-dark">
                {SERVICE_USAGE_STRINGS.action}
              </span>
            )}
            widthClassName="w-[640px] max-w-full"
          >
            <ServiceUsageModal
              key={usageService.id}
              variant="panel"
              kind="sandbox"
              scope="system"
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

export default SystemSandboxServicesPage;
