import React, { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Users, Pencil, Trash2, Brain } from 'lucide-react';
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
  const { t } = useTranslation('common');
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
      setError(errorMessage(err, t('systemEmbeddingServicesPage.loadFailed')));
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
          ? t('systemEmbeddingServicesPage.updating')
          : t('systemEmbeddingServicesPage.creating'),
        success: editingService
          ? t('systemEmbeddingServicesPage.updated')
          : t('systemEmbeddingServicesPage.created'),
        error: (err) => errorMessage(
          err,
          editingService
            ? t('systemEmbeddingServicesPage.updateFailed')
            : t('systemEmbeddingServicesPage.createFailed'),
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
    if (!service) throw new Error(t('systemEmbeddingServicesPage.serviceNotFound'));
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
        title: t('systemEmbeddingServicesPage.deleteTitle'),
        message: (
          <>
            <p>{t('systemEmbeddingServicesPage.impactCheckFailed', {
              error: errorMessage(err, t('systemEmbeddingServicesPage.unknownError')),
            })}</p>
            <p className="mt-2">{t('systemEmbeddingServicesPage.deleteAnyway')}</p>
          </>
        ),
        variant: 'danger',
        confirmLabel: t('embeddingServicesPage.actions.delete'),
      });
      if (!result) return;
      await runDelete(svc.service_id);
      return;
    }

    const ok = await confirm({
      title: t('systemEmbeddingServicesPage.deleteTitle'),
      message:
        impact.affected_silos_count > 0 ? (
          <div>
            <p>
              {t('systemEmbeddingServicesPage.deletionImpact', {
                name: svc.name,
                siloCount: impact.affected_silos_count,
                siloLabel: t('systemEmbeddingServicesPage.silo', { count: impact.affected_silos_count }),
                appCount: impact.affected_apps_count,
                appLabel: t('systemEmbeddingServicesPage.app', { count: impact.affected_apps_count }),
              })}
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
          <p>{t('systemEmbeddingServicesPage.deleteMessage', { name: svc.name })}</p>
        ),
      variant: 'danger',
      confirmLabel: t('embeddingServicesPage.actions.delete'),
    });
    if (!ok) return;
    await runDelete(svc.service_id);
  };

  const runDelete = async (serviceId: number) => {
    const result = await mutate(
      () => apiService.deleteSystemEmbeddingService(serviceId),
      {
        loading: t('systemEmbeddingServicesPage.deleting'),
        success: t('systemEmbeddingServicesPage.deleted'),
        error: (err) => errorMessage(err, t('systemEmbeddingServicesPage.deleteFailed')),
      },
    );
    if (result === undefined) return;
    settingsCache.invalidateSystemServiceCaches();
    await fetchServices();
  };

  const columns: TableColumn<SystemEmbeddingService>[] = [
    {
      header: t('embeddingServicesPage.columns.name'),
      className: 'px-6 py-4 whitespace-nowrap',
      render: (svc) => (
        <div className="flex items-center gap-2">
          <BackgroundImage icon={Brain} variant="marron" size={32} iconSize={16} />
          <button
            type="button"
            onClick={() => handleOpenEdit(svc)}
            className="text-left text-sm font-medium text-fg dark:text-fg-dark"
          >
            {svc.name}
          </button>
          
        </div>
      ),
    },
    {
      header: t('embeddingServicesPage.columns.provider'),
      accessor: 'provider',
      className: 'px-6 py-4 whitespace-nowrap text-xs text-fg-secondary dark:text-fg-secondary-dark',
    },
    {
      header: t('embeddingServicesPage.columns.model'),
      accessor: 'model_name',
      className: 'px-6 py-4 whitespace-nowrap text-xs text-fg-secondary dark:text-fg-secondary-dark',
    },
    {
      header: t('embeddingServicesPage.columns.status'),
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
      header: t('embeddingServicesPage.columns.actions'),
      sticky: 'right' as const,
      headerClassName: 'text-right',
      className: 'px-6 py-4 whitespace-nowrap text-right',
      render: (svc) => (
        <div className="inline-flex justify-end">
          <ActionDropdown
            size="sm"
            triggerAriaLabel={t('embeddingServicesPage.actions.menuForService', { name: svc.name })}
            actions={[
              {
                label: SERVICE_USAGE_STRINGS.action,
                icon: <Users className="w-4 h-4" />,
                onClick: () => setUsageService({ id: svc.service_id, name: svc.name }),
              },
              testAction(svc.service_id, svc.name, () => testConnection(svc.service_id)),
              {
                label: t('embeddingServicesPage.actions.edit'),
                icon: <Pencil className="w-4 h-4" />,
                onClick: () => handleOpenEdit(svc),
              },
              {
                label: t('embeddingServicesPage.actions.delete'),
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

  if (isLoading) return (
    <div className="space-y-6">
            {/* Page Header */}
            <div className="flex items-center justify-between">
              <Title variant='titPrincipal' titulo={t('systemEmbeddingServicesPage.title')} subtitulo={t('systemEmbeddingServicesPage.subtitle')}></Title>
            </div>
    
            <LoadingState variant="page" message={t('systemEmbeddingServicesPage.loading')} />
          </div>
  ) ;
  if (error) return <ErrorState error={error} onRetry={fetchServices} />;

  return (
    <div className="mx-auto space-y-6">
      <div className="flex items-start justify-between gap-4">
        <Title variant='titPrincipal' titulo={t('systemEmbeddingServicesPage.title')} subtitulo={t('systemEmbeddingServicesPage.subtitle')}></Title>
        <ButtonApp
              label={t('embeddingServicesPage.addService')}
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
        emptyIcon={<BackgroundImage icon={Brain} size={64} iconSize={32} />}
        emptyMessage={t('systemEmbeddingServicesPage.empty')}
      />

      {services.length === 0 && (
        <div className="text-center py-6">
          <ButtonApp
            label={t('embeddingServicesPage.addFirstService')}
            onClick={handleOpenCreate}
            variant="primary"
            size="medium"
          />
        </div>
      )}

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
          variant="panel"
          kind="embedding"
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
            title={t('systemEmbeddingServicesPage.title')}
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
              kind="embedding"
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

export default SystemEmbeddingServicesPage;
