import { useState, useEffect } from 'react';
import { Link, useParams, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { Upload, Database, Gamepad2, ArrowDownToLine, Pencil, Trash2 } from 'lucide-react';
import { apiService } from '../services/api';
import ActionDropdown from '../components/ui/ActionDropdown';
import Table from '../components/ui/Table';
import { useAppRole } from '../hooks/useAppRole';
import { AppRole } from '../types/roles';
import ReadOnlyBanner from '../components/ui/ReadOnlyBanner';
import ImportModal, { type ConflictMode, type ImportResponse } from '../components/ui/ImportModal';
import type { ServiceOptionLike } from '../utils/serviceLifecycle';
import { useConfirm } from '../contexts/ConfirmContext';
import { useApiMutation } from '../hooks/useApiMutation';
import { errorMessage } from '../constants/messages';
import Title from '../components/ui/Title';
import ButtonApp from '../components/ui/ButtonApp';
import Alert from '../components/ui/Alert';
import ButtonLink from '../components/ui/ButtonLink';
import BackgroundImage from '../components/ui/BackgroundImage';
import { LoadingState } from '../components/ui/LoadingState';
import type { ServiceLifecycleWarning } from '../types/services';
import ServiceLifecycleAlert from '../components/services/ServiceLifecycleAlert';

// ...existing code...
interface Silo {
  silo_id: number;
  name: string;
  description?: string;
  type?: string;
  created_at?: string;
  docs_count: number;
  vector_db_type?: string;
  lifecycle_warnings?: ServiceLifecycleWarning[];
}

function SilosPage() {
  const { t, i18n } = useTranslation('common');
  const { appId } = useParams();
  const { hasMinRole, userRole } = useAppRole(appId);
  const canEdit = hasMinRole(AppRole.EDITOR);
  const confirm = useConfirm();
  const mutate = useApiMutation();

  const [silos, setSilos] = useState<Silo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showImportModal, setShowImportModal] = useState(false);
  const [requiresEmbeddingServiceSelection, setRequiresEmbeddingServiceSelection] = useState(false);
  const [availableEmbeddingServices, setAvailableEmbeddingServices] = useState<ServiceOptionLike[]>([]);
  const [selectedEmbeddingServiceId, setSelectedEmbeddingServiceId] = useState<number | undefined>(undefined);
  const navigate = useNavigate();

  // Load silos from the API
  useEffect(() => {
    void loadSilos();
  }, [appId]);

  async function loadSilos() {
    if (!appId) return;
    
    try {
      setLoading(true);
      setError(null);
      const response = await apiService.getSilos(Number.parseInt(appId));
      setSilos(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('silosPage.loadFailed'));
      console.error('Error loading silos:', err);
    } finally {
      setLoading(false);
    }
  }

  async function handleDelete(siloId: number) {
    if (!appId) return;

    const target = silos.find((s) => s.silo_id === siloId);
    const ok = await confirm({
      title: t('silosPage.confirmDeleteTitle'),
      message: target
        ? t('silosPage.confirmDeleteMessage', { name: target.name })
        : t('silosPage.confirmDeleteFallback'),
      variant: 'danger',
      confirmLabel: t('silosPage.actions.delete'),
    });
    if (!ok) return;

    const result = await mutate(
      () => apiService.deleteSilo(Number.parseInt(appId), siloId),
      {
        loading: t('silosPage.deleting'),
        success: t('silosPage.deleted'),
        error: (err) => errorMessage(err, t('silosPage.deleteFailed')),
      },
    );
    if (result === undefined) return;

    setSilos(silos.filter((s) => s.silo_id !== siloId));
  }

  async function handleExport(siloId: number) {
    if (!appId) return;

    try {
      const silo = silos.find(s => s.silo_id === siloId);
      const siloName = silo?.name || 'silo';
      
      const blob = await apiService.exportSilo(Number.parseInt(appId), siloId);
      
      // Generate filename
      const timestamp = new Date().toISOString().split('T')[0];
      const sanitizedName = siloName.replaceAll(/[^a-z0-9]/gi, '_').toLowerCase();
      const filename = `silo-${sanitizedName}-${timestamp}.json`;
      
      // Download
      const url = globalThis.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      globalThis.URL.revokeObjectURL(url);
      a.remove();

      toast.warning(t('silosPage.exported'), { duration: 7000 });
    } catch (err) {
      toast.error(errorMessage(err, t('silosPage.exportFailed')));
      console.error('Error exporting silo:', err);
    }
  }

  async function handleImport(
    file: File,
    conflictMode: ConflictMode,
    newName?: string
  ): Promise<ImportResponse> {
    if (!appId) {
      throw new Error(t('silosPage.appIdRequired'));
    }

    try {
      // Parse file to check if embedding service selection is needed
      if (!requiresEmbeddingServiceSelection) {
        const fileContent = await file.text();
        const fileData = JSON.parse(fileContent);
        
        // Check if embedding service is needed but not bundled
        if (fileData.silo?.embedding_service_name && !fileData.embedding_service) {
          // Fetch available embedding services
          const services: ServiceOptionLike[] = await apiService.getEmbeddingServices(Number.parseInt(appId));
          setAvailableEmbeddingServices(services);
          setRequiresEmbeddingServiceSelection(true);
          
          return {
            success: false,
            message: t('silosPage.selectEmbeddingService'),
          };
        }
      }

      // Perform import
      const result = await apiService.importSilo(
        Number.parseInt(appId),
        file,
        conflictMode,
        newName,
        selectedEmbeddingServiceId
      );

      if (result.success) {
        setShowImportModal(false);
        toast.success(result.message || t('silosPage.imported'));
        void loadSilos();

        // Reset embedding service selection state
        setRequiresEmbeddingServiceSelection(false);
        setSelectedEmbeddingServiceId(undefined);
      }

      return result;
    } catch (err: any) {
      return {
        success: false,
        message: err?.message || t('silosPage.importFailed'),
      };
    }
  } 

  if (loading) {
    return (
      <div className="space-y-6">
        {/* Page Header */}
        <div className="flex items-center justify-between">
          <Title variant='titSecundario' titulo={t('silosPage.title')} subtitulo={t('silosPage.subtitle')}></Title>
        </div>

        <LoadingState variant="page" message={t('silosPage.loading')} />
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-6">
        {/* Page Header */}
        <div className="flex items-center justify-between">
          <Title variant='titSecundario' titulo={t('silosPage.title')} subtitulo={t('silosPage.subtitle')}></Title>
        </div>

        <Alert
          type="error"
          title={t('silosPage.loadErrorTitle')}
          message={(
            <>
              {error}
              <button type="button" onClick={() => loadSilos()} className="mt-2 block underline">
                {t('silosPage.retry')}
              </button>
            </>
          )}
        />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <Title variant='titSecundario' titulo={t('silosPage.title')} subtitulo={t('silosPage.subtitle')}></Title>
        <div className="flex items-center space-x-3">
          {hasMinRole(AppRole.ADMINISTRATOR) && (
            <ButtonApp
              label={t('silosPage.importSilo')}
              icon={<Upload className="w-4 h-4" />}
              onClick={() => setShowImportModal(true)}
              variant="secondary"
              size="medium"
            />
          )}
          {canEdit && (
            <ButtonLink
              to={`/apps/${appId}/silos/new`}
              label={t('silosPage.createSilo')}
              variant="primary"
              size="medium"
              icon={<span aria-hidden="true">+</span>}
            />
          )}
        </div>
      </div>

      {!canEdit && <ReadOnlyBanner userRole={userRole} minRole={AppRole.EDITOR} />}

      {/* Silos List */}
      <Table
          data={silos}
          stickyEdgeColumns
          keyExtractor={(silo) => silo.silo_id.toString()}
          columns={[
            {
              header: t('silosPage.columns.name'),
              render: (silo) => (
                <div className="flex items-center">
                  <div className="flex-shrink-0 h-10 w-10">
                    <BackgroundImage variant="marron" icon={Database} size={28}
                      iconSize={14}
                      className="rounded-lg"/>
                  </div>
                  <div className="ml-4">
                    <div className="text-sm font-medium text-gray-900">
                      {canEdit ? (
                        <Link
                          to={`/apps/${appId}/silos/${silo.silo_id}`}
                          className="text-sm font-medium text-fg dark:text-fg-dark"
                        >
                          {silo.name}
                        </Link>
                      ) : (
                        <span className="text-sm font-medium text-fg dark:text-fg-dark">
                          {silo.name}
                        </span>
                      )}
                    </div>
                    <ServiceLifecycleAlert warnings={silo.lifecycle_warnings} variant="compact" className="mt-0.5" />
                  </div>
                </div>
              )
            },
            {
              header: t('silosPage.columns.description'),
              accessor: 'description',
              className: 'px-6 py-4 whitespace-nowrap text-xs text-fg-secondary dark:text-fg-secondary-dark'
            },
            {
              header: t('silosPage.columns.type'),
              render: (silo) => (
                <span className="inline-flex px-2 py-1 text-xs font-semibold rounded-full bg-gray-100 text-gray-800">
                  {silo.type || t('silosPage.custom')}
                </span>
              )
            },
            {
              header: t('silosPage.columns.vectorDb'),
              accessor: 'vector_db_type',
              render: (silo) => silo.vector_db_type || t('silosPage.unknown'),
              className: "text-xs text-fg-secondary dark:text-fg-secondary-dark"
            },
            {
              header: t('silosPage.columns.documents'),
              render: (silo) => t('silosPage.documentCount', { count: silo.docs_count }),
              className: 'text-xs text-fg-secondary dark:text-fg-secondary-dark'
            },
            {
              header: t('silosPage.columns.created'),
              render: (silo) => silo.created_at ? new Date(silo.created_at).toLocaleDateString(i18n.language) : t('silosPage.notAvailable'),
              className: 'text-xs text-fg-secondary dark:text-fg-secondary-dark'
            },
            {
              header: t('silosPage.columns.actions'),
              sticky: 'right',
              headerClassName: 'px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider',
              className: 'text-xs text-fg-secondary dark:text-fg-secondary-dark',
              render: (silo) => (
                <ActionDropdown
                  actions={[
                    {
                      label: t('silosPage.actions.playground'),
                      onClick: () => navigate(`/apps/${appId}/silos/${silo.silo_id}/playground`),
                      icon: <Gamepad2 className="w-4 h-4" />,
                      variant: 'warning'
                    },
                    {
                      label: t('silosPage.actions.export'),
                      onClick: () => { void handleExport(silo.silo_id); },
                      icon: <ArrowDownToLine className="w-4 h-4" />,
                      variant: 'primary' as const
                    },
                    ...(canEdit ? [
                      {
                        label: t('silosPage.actions.edit'),
                        onClick: () => navigate(`/apps/${appId}/silos/${silo.silo_id}`),
                        icon: <Pencil className="w-4 h-4" />,
                        variant: 'primary' as const
                      },
                      {
                        label: t('silosPage.actions.delete'),
                        onClick: () => { void handleDelete(silo.silo_id); },
                        icon: <Trash2 className="w-4 h-4" />,
                        variant: 'danger' as const
                      }
                    ] : [])
                  ]}
                  size="sm"
                />
              )
            }
          ]}
          emptyIcon={<BackgroundImage icon={Database} size={64} iconSize={32} />}
          emptyMessage={t('silosPage.emptyTitle')}
          emptySubMessage={t('silosPage.emptyDescription')}
          loading={loading}
      />

      {!loading && canEdit && silos.length === 0 && (
        <div className="text-center py-6">
          <ButtonLink
            to={`/apps/${appId}/silos/new`}
            label={t('silosPage.createFirst')}
            variant="primary"
            size="medium"
            icon={<span aria-hidden="true">+</span>}
          />
        </div>
      )}

      {/* Import Modal */}
      <ImportModal
        isOpen={showImportModal}
        onClose={() => {
          setShowImportModal(false);
          setRequiresEmbeddingServiceSelection(false);
          setSelectedEmbeddingServiceId(undefined);
        }}
        onImport={handleImport}
        componentType="silo"
        componentLabel={t('silosPage.silo')}
        requiresEmbeddingServiceSelection={requiresEmbeddingServiceSelection}
        availableEmbeddingServices={availableEmbeddingServices}
        selectedEmbeddingServiceId={selectedEmbeddingServiceId}
        onEmbeddingServiceChange={setSelectedEmbeddingServiceId}
      />
    </div>
  );
}

export default SilosPage; 