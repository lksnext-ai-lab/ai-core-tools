import { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { BarChart2, Upload, ArrowDownToLine, Pencil, Trash2} from 'lucide-react';
import Modal from '../../components/ui/Modal';
import DataStructureForm from '../../components/forms/DataStructureForm';
import { apiService } from '../../services/api';
import ActionDropdown from '../../components/ui/ActionDropdown';
import { useSettingsCache } from '../../contexts/SettingsCacheContext';
import { useAppRole } from '../../hooks/useAppRole';
import { AppRole } from '../../types/roles';
import ReadOnlyBanner from '../../components/ui/ReadOnlyBanner';
import Alert from '../../components/ui/Alert';
import Table from '../../components/ui/Table';
import ImportModal, { type ConflictMode, type ImportResponse } from '../../components/ui/ImportModal';
import { useConfirm } from '../../contexts/ConfirmContext';
import { useApiMutation } from '../../hooks/useApiMutation';
import { errorMessage } from '../../constants/messages';
import { LoadingState } from '../../components/ui/LoadingState';
import { Spinner } from '../../components/ui/Spinner';
import { Title } from '../../components/ui/Title';
import ButtonApp from '../../components/ui/ButtonApp';
import Badge from '../../components/ui/Badge';
import BackgroundImage from '../../components/ui/BackgroundImage';

interface DataStructure {
  parser_id: number;
  name: string;
  description: string;
  field_count: number;
  created_at: string;
}

function DataStructuresPage() {
  const { appId } = useParams();
  const { t, i18n } = useTranslation('common');
  const settingsCache = useSettingsCache();
  const { hasMinRole, userRole } = useAppRole(appId);
  const canEdit = hasMinRole(AppRole.ADMINISTRATOR);
  const confirm = useConfirm();
  const mutate = useApiMutation();
  const [dataStructures, setDataStructures] = useState<DataStructure[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingStructure, setEditingStructure] = useState<any>(null);
  const [showImportModal, setShowImportModal] = useState(false);
  const [exportingParserId, setExportingParserId] = useState<number | null>(null);

  // Load data structures from cache or API
  useEffect(() => {
    void loadDataStructures();
  }, [appId]);

  async function loadDataStructures() {
    if (!appId) return;
    
    // Check if we have cached data first
    const cachedData = settingsCache.getDataStructures(appId);
    if (cachedData) {
      setDataStructures(cachedData);
      setLoading(false);
      return;
    }
    
    // If no cache, load from API
    try {
      setLoading(true);
      setError(null);
      const response = await apiService.getOutputParsers(Number.parseInt(appId));
      setDataStructures(response);
      // Cache the response
      settingsCache.setDataStructures(appId, response);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('dataStructuresPage.loadFailed'));
      console.error('Error loading data structures:', err);
    } finally {
      setLoading(false);
    }
  }

  async function forceReloadDataStructures() {
    if (!appId) return;
    
    try {
      setLoading(true);
      setError(null);
      const response = await apiService.getOutputParsers(Number.parseInt(appId));
      setDataStructures(response);
      // Cache the response
      settingsCache.setDataStructures(appId, response);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('dataStructuresPage.loadFailed'));
      console.error('Error loading data structures:', err);
    } finally {
      setLoading(false);
    }
  }

  async function handleDelete(structure: DataStructure) {
    if (!appId) return;

    const ok = await confirm({
      title: t('servicesManager.confirmDeleteTitle', { entity: t('dataStructuresPage.entity') }),
      message: t('dataStructuresPage.confirmDeleteNamed', { name: structure.name }),
      variant: 'danger',
      confirmLabel: t('dataStructuresPage.actions.delete'),
      cancelLabel: t('cancel'),
    });
    if (!ok) return;

    const result = await mutate(
      () => apiService.deleteOutputParser(Number.parseInt(appId), structure.parser_id),
      {
        loading: t('dataStructuresPage.deleting'),
        success: t('dataStructuresPage.deleted'),
        error: (err) => errorMessage(err, t('dataStructuresPage.deleteFailed')),
      },
    );
    if (result === undefined) return;

    const newDataStructures = dataStructures.filter((ds) => ds.parser_id !== structure.parser_id);
    setDataStructures(newDataStructures);
    settingsCache.setDataStructures(appId, newDataStructures);
  }

  async function handleCreateStructure() {
    if (!appId) return;
    
    try {
      // Load a blank structure with available parsers list
      const blankStructure = await apiService.getOutputParser(Number.parseInt(appId), 0);
      setEditingStructure(blankStructure);
      setIsModalOpen(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('dataStructuresPage.loadParserOptionsFailed'));
      console.error('Error loading blank structure:', err);
    }
  }

  async function handleEditStructure(parserId: number) {
    if (!appId) return;
    
    try {
      const structure = await apiService.getOutputParser(Number.parseInt(appId), parserId);
      setEditingStructure(structure);
      setIsModalOpen(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('dataStructuresPage.loadDetailsFailed'));
      console.error('Error loading data structure:', err);
    }
  }

  async function handleSaveStructure(data: any) {
    if (!appId) return;

    const isUpdate = Boolean(editingStructure && editingStructure.parser_id !== 0);

    const result = await mutate(
      () =>
        isUpdate
          ? apiService.updateOutputParser(Number.parseInt(appId), editingStructure.parser_id, data)
          : apiService.createOutputParser(Number.parseInt(appId), data),
      {
        loading: isUpdate ? t('dataStructuresPage.updating') : t('dataStructuresPage.creating'),
        success: isUpdate ? t('dataStructuresPage.updated') : t('dataStructuresPage.created'),
        error: (err) => errorMessage(err, t('dataStructuresPage.saveFailed')),
      },
    );
    if (result === undefined) return;

    settingsCache.invalidateDataStructures(appId);
    try {
      await forceReloadDataStructures();
    } catch (err) {
      console.error('Refetch after save failed:', err);
    }
    setIsModalOpen(false);
    setEditingStructure(null);
  }

  function handleCloseModal() {
    setIsModalOpen(false);
    setEditingStructure(null);
  }

  async function handleExport(parserId: number) {
    if (!appId) return;
    setExportingParserId(parserId);

    try {
      const blob = await apiService.exportOutputParser(Number.parseInt(appId), parserId);

      const parser = dataStructures.find((p) => p.parser_id === parserId);
      const parserName = parser?.name || 'output-parser';
      const sanitizedName = parserName.replaceAll(/[^a-z0-9]/gi, '-').toLowerCase();
      const timestamp = new Date().toISOString().split('T')[0];
      const filename = `output-parser-${sanitizedName}-${timestamp}.json`;

      const url = globalThis.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      globalThis.URL.revokeObjectURL(url);
      a.remove();
      toast.success(t('dataStructuresPage.exported'));
    } catch (err) {
      toast.error(errorMessage(err, t('dataStructuresPage.exportFailed')));
    } finally {
      setExportingParserId(null);
    }
  }

  async function handleImport(
    file: File,
    conflictMode: ConflictMode,
    newName?: string
  ): Promise<ImportResponse> {
    if (!appId) throw new Error(t('dataStructuresPage.appIdNotFound'));
    
    try {
      const result = await apiService.importOutputParser(
        Number.parseInt(appId),
        file,
        conflictMode,
        newName
      );
      
      if (result.success) {
        setShowImportModal(false);
        toast.success(result.message || t('dataStructuresPage.imported'));
        await forceReloadDataStructures();
      }

      return result;
    } catch (err) {
      toast.error(errorMessage(err, t('dataStructuresPage.importFailed')));
      throw err;
    }
  }

  if (loading) {
    return (
      
      <div className="space-y-6">
        {/* Page Header */}
        <div className="flex items-center justify-between">
          <Title variant="titSecundario" titulo={t('dataStructuresPage.title')} subtitulo={t('dataStructuresPage.subtitle')} />
        </div>

        <LoadingState variant="page" message={t('dataStructuresPage.loading')} />
      </div>

    );
  }

  if (error) {
    return (
      <div className="space-y-6">
        {/* Page Header */}
        <div className="flex items-center justify-between">
          <Title variant="titSecundario" titulo={t('dataStructuresPage.title')} subtitulo={t('dataStructuresPage.subtitle')} />
        </div>

        <Alert type="error" message={error} onDismiss={() => loadDataStructures()} />
      </div>
    );
  }

  return (
    
      <div className="p-6">
        {/* Header */}
        <div className="flex justify-between items-center mb-6">
          <div>
            <Title variant="titSecundario" titulo={t('dataStructuresPage.title')} subtitulo={t('dataStructuresPage.subtitle')} />
          </div>
          {canEdit && (
            <div className="flex gap-2">
              <ButtonApp
                label={t('dataStructuresPage.import')}
                onClick={() => setShowImportModal(true)}
                icon={<Upload className="w-4 h-4" />}
                variant="secondary"
                size="medium"
              />
              <ButtonApp
                label={t('dataStructuresPage.createStructure')}
                onClick={handleCreateStructure}
                icon={<span aria-hidden="true">+</span>}
                variant="primary"
                size="medium"
              />
            </div>
          )}
        </div>
        
        {/* Read-only banner for non-admins */}
        {!canEdit && <ReadOnlyBanner userRole={userRole} minRole={AppRole.ADMINISTRATOR} />}

        {/* Data Structures Table */}
        <Table
          data={dataStructures}
          stickyEdgeColumns
          keyExtractor={(structure) => structure.parser_id.toString()}
          columns={[
            {
              header: t('dataStructuresPage.columns.name'),
              render: (structure) => (
                <div className="flex items-center">
                 <BackgroundImage icon={BarChart2} iconSize={17} size={34} className="mr-2"/>
                  {canEdit ? (
                    <button
                      type="button"
                      className="text-sm font-medium text-fg dark:text-fg-dark transition-colors text-left"
                      onClick={() => void handleEditStructure(structure.parser_id)}
                    >
                      {structure.name}
                    </button>
                  ) : (
                    <span className="text-sm font-medium text-fg dark:text-fg-dark">
                      {structure.name}
                    </span>
                  )}
                </div>
              )
            },
            {
              header: t('dataStructuresPage.columns.description'),
              render: (structure) => (
                <div className="text-xs text-fg-secondary dark:text-fg-secondary-dark max-w-xs truncate">
                  {structure.description || t('dataStructuresPage.noDescription')}
                </div>
              ),
              className: 'px-6 py-4'
            },
            {
              header: t('dataStructuresPage.columns.fields'),
              render: (structure) => (
                <Badge variant='success' label={t('dataStructuresPage.fieldCount', { count: structure.field_count })} />
              )
            },
            {
              header: t('dataStructuresPage.columns.created'),
              render: (structure) => structure.created_at ? new Date(structure.created_at).toLocaleDateString(i18n.resolvedLanguage) : t('dataStructuresPage.notAvailable'),
              className: 'px-6 py-4 whitespace-nowrap text-xs text-fg-secondary dark:text-fg-secondary-dark'
            },
            {
              header: t('dataStructuresPage.columns.actions'),
              sticky: 'right',
              render: (structure) => (
                canEdit ? (
                  <ActionDropdown
                    actions={[
                      {
                        label: exportingParserId === structure.parser_id ? t('dataStructuresPage.exporting') : t('dataStructuresPage.export'),
                        onClick: () => { void handleExport(structure.parser_id); },
                        icon: exportingParserId === structure.parser_id ? <Spinner size="sm" tone="current" /> : <ArrowDownToLine className="w-4 h-4" />,
                        variant: 'primary' as const,
                        disabled: exportingParserId === structure.parser_id
                      },
                      {
                        label: t('dataStructuresPage.actions.edit'),
                        onClick: () => { void handleEditStructure(structure.parser_id); },
                        icon: <Pencil className="w-4 h-4" />,
                        variant: 'primary'
                      },
                      {
                        label: t('dataStructuresPage.actions.delete'),
                        onClick: () => { void handleDelete(structure); },
                        icon: <Trash2 className="w-4 h-4" />,
                        variant: 'danger'
                      }
                    ]}
                    size="sm"
                    triggerAriaLabel={t('dataStructuresPage.actions.menuForStructure', { name: structure.name })}
                  />
                ) : (
                  <span className="text-gray-400 text-sm">{t('dataStructuresPage.viewOnly')}</span>
                )
              )
            }
          ]}
          emptyIcon={<BackgroundImage icon={BarChart2} size={64} iconSize={32} />}
          emptyMessage={t('dataStructuresPage.empty.title')}
          emptySubMessage={t('dataStructuresPage.empty.subtitle')}
          loading={loading}
        />

        {!loading && dataStructures.length === 0 && (
          <div className="text-center py-6">
            <ButtonApp
              label={t('dataStructuresPage.createFirstStructure')}
              onClick={handleCreateStructure}
              variant="primary"
              size="medium"
            />
          </div>
        )}

        {/* Info Boxes */}
        <div className="mt-6 space-y-4">
          {/* Main Info */}
          <Alert
            type="info"
            title={t('dataStructuresPage.about.title')}
            message={t('dataStructuresPage.about.message')}
          />

          {/* Examples */}
          <Alert
            type="info"
            title={t('dataStructuresPage.useCases.title')}
            message={(
              <ul className="list-disc list-inside space-y-1">
                <li><strong>{t('dataStructuresPage.useCases.documentAnalysis')}:</strong> {t('dataStructuresPage.useCases.documentAnalysisHelp')}</li>
                <li><strong>{t('dataStructuresPage.useCases.agentResponses')}:</strong> {t('dataStructuresPage.useCases.agentResponsesHelp')}</li>
                <li><strong>{t('dataStructuresPage.useCases.dataValidation')}:</strong> {t('dataStructuresPage.useCases.dataValidationHelp')}</li>
                <li><strong>{t('dataStructuresPage.useCases.apiIntegration')}:</strong> {t('dataStructuresPage.useCases.apiIntegrationHelp')}</li>
                <li><strong>{t('dataStructuresPage.useCases.complexObjects')}:</strong> {t('dataStructuresPage.useCases.complexObjectsHelp')}</li>
              </ul>
            )}
          />
        </div>

        {/* Create/Edit Modal */}
        <Modal
          isOpen={isModalOpen}
          onClose={handleCloseModal}
          title={editingStructure ? t('dataStructuresPage.editTitle') : t('dataStructuresPage.createTitle')}
          size="xlarge"
        >
          <DataStructureForm
            dataStructure={editingStructure}
            onSubmit={handleSaveStructure}
            onCancel={handleCloseModal}
          />
        </Modal>

        {/* Import Modal */}
        <ImportModal
          isOpen={showImportModal}
          onClose={() => setShowImportModal(false)}
          onImport={handleImport}
          componentType="output_parser"
          componentLabel={t('dataStructuresPage.componentLabel')}
        />
      </div>
    
  );
}

export default DataStructuresPage; 