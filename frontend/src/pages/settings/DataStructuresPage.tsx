import { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
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
import { MESSAGES, errorMessage } from '../../constants/messages';
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
      setError(err instanceof Error ? err.message : 'Failed to load data structures');
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
      setError(err instanceof Error ? err.message : 'Failed to load data structures');
      console.error('Error loading data structures:', err);
    } finally {
      setLoading(false);
    }
  }

  async function handleDelete(structure: DataStructure) {
    if (!appId) return;

    const ok = await confirm({
      title: MESSAGES.CONFIRM_DELETE_TITLE('data structure'),
      message: `Are you sure you want to delete "${structure.name}"? This action cannot be undone.`,
      variant: 'danger',
      confirmLabel: 'Delete',
    });
    if (!ok) return;

    const result = await mutate(
      () => apiService.deleteOutputParser(Number.parseInt(appId), structure.parser_id),
      {
        loading: MESSAGES.DELETING('data structure'),
        success: MESSAGES.DELETED('data structure'),
        error: (err) => errorMessage(err, MESSAGES.DELETE_FAILED('data structure')),
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
      setError(err instanceof Error ? err.message : 'Failed to load parser options');
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
      setError(err instanceof Error ? err.message : 'Failed to load data structure details');
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
        loading: isUpdate ? MESSAGES.UPDATING('data structure') : MESSAGES.CREATING('data structure'),
        success: isUpdate ? MESSAGES.UPDATED('data structure') : MESSAGES.CREATED('data structure'),
        error: (err) => errorMessage(err, MESSAGES.SAVE_FAILED('data structure')),
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
      toast.success(MESSAGES.EXPORTED('data structure'));
    } catch (err) {
      toast.error(errorMessage(err, MESSAGES.EXPORT_FAILED('data structure')));
    } finally {
      setExportingParserId(null);
    }
  }

  async function handleImport(
    file: File,
    conflictMode: ConflictMode,
    newName?: string
  ): Promise<ImportResponse> {
    if (!appId) throw new Error('App ID not found');
    
    try {
      const result = await apiService.importOutputParser(
        Number.parseInt(appId),
        file,
        conflictMode,
        newName
      );
      
      if (result.success) {
        setShowImportModal(false);
        toast.success(result.message || MESSAGES.IMPORTED('data structure'));
        await forceReloadDataStructures();
      }

      return result;
    } catch (err) {
      toast.error(errorMessage(err, MESSAGES.IMPORT_FAILED('data structure')));
      throw err;
    }
  }

  if (loading) {
    return (
      
      <div className="space-y-6">
        {/* Page Header */}
        <div className="flex items-center justify-between">
          <Title variant="titSecundario" titulo="Data Structures" subtitulo='Define schemas for structured data extraction and validation'/>
        </div>

        <LoadingState variant="page" message="Loading data structures..." />
      </div>

    );
  }

  if (error) {
    return (
      <div className="space-y-6">
        {/* Page Header */}
        <div className="flex items-center justify-between">
          <Title variant="titSecundario" titulo="Data Structures" subtitulo='Define schemas for structured data extraction and validation'/>
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
            <Title variant="titSecundario" titulo="Data Structures" subtitulo='Define schemas for structured data extraction and validation'/>
          </div>
          {canEdit && (
            <div className="flex gap-2">
              <ButtonApp
                label="Import"
                onClick={() => setShowImportModal(true)}
                icon={<Upload className="w-4 h-4" />}
                variant="secondary"
                size="medium"
              />
              <ButtonApp
                label="Create Data Structure"
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
          keyExtractor={(structure) => structure.parser_id.toString()}
          columns={[
            {
              header: 'Name',
              render: (structure) => (
                <div className="flex items-center">
                 <BackgroundImage icon={BarChart2} iconSize={20} size={40} className="mr-2"/>
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
              header: 'Description',
              render: (structure) => (
                <div className="text-xs text-fg-secondary dark:text-fg-secondary-dark max-w-xs truncate">
                  {structure.description || 'No description'}
                </div>
              ),
              className: 'px-6 py-4'
            },
            {
              header: 'Fields',
              render: (structure) => (
                <Badge variant='success' label={`${structure.field_count} field${structure.field_count === 1 ? '' : 's'}`} />
              )
            },
            {
              header: 'Created',
              render: (structure) => structure.created_at ? new Date(structure.created_at).toLocaleDateString() : 'N/A',
              className: 'px-6 py-4 whitespace-nowrap text-xs text-fg-secondary dark:text-fg-secondary-dark'
            },
            {
              header: 'Actions',
              render: (structure) => (
                canEdit ? (
                  <ActionDropdown
                    actions={[
                      {
                        label: exportingParserId === structure.parser_id ? 'Exporting...' : 'Export',
                        onClick: () => { void handleExport(structure.parser_id); },
                        icon: exportingParserId === structure.parser_id ? <Spinner size="sm" tone="current" /> : <ArrowDownToLine className="w-4 h-4" />,
                        variant: 'primary' as const,
                        disabled: exportingParserId === structure.parser_id
                      },
                      {
                        label: 'Edit',
                        onClick: () => { void handleEditStructure(structure.parser_id); },
                        icon: <Pencil className="w-4 h-4" />,
                        variant: 'primary'
                      },
                      {
                        label: 'Delete',
                        onClick: () => { void handleDelete(structure); },
                        icon: <Trash2 className="w-4 h-4" />,
                        variant: 'danger'
                      }
                    ]}
                    size="sm"
                  />
                ) : (
                  <span className="text-gray-400 text-sm">View only</span>
                )
              )
            }
          ]}
          emptyIcon={<BarChart2 className="w-10 h-10 text-gray-300" />}
          emptyMessage="No Data Structures"
          emptySubMessage="Create your first data structure to define schemas for structured data extraction."
          loading={loading}
        />

        {!loading && dataStructures.length === 0 && (
          <div className="text-center py-6">
            <ButtonApp
              label="Create First Data Structure"
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
            title="About Data Structures"
            message="Data structures are dynamic schemas that define the format for structured data extraction. They automatically generate Pydantic models for validation and can reference other structures for complex nested data patterns."
          />

          {/* Examples */}
          <Alert
            type="info"
            title="Common Use Cases"
            message={(
              <ul className="list-disc list-inside space-y-1">
                <li><strong>Document Analysis:</strong> Extract structured metadata from documents</li>
                <li><strong>Agent Responses:</strong> Ensure consistent output format from AI agents</li>
                <li><strong>Data Validation:</strong> Validate and type-check extracted information</li>
                <li><strong>API Integration:</strong> Define schemas for external data sources</li>
                <li><strong>Complex Objects:</strong> Build nested structures with references</li>
              </ul>
            )}
          />
        </div>

        {/* Create/Edit Modal */}
        <Modal
          isOpen={isModalOpen}
          onClose={handleCloseModal}
          title={editingStructure ? 'Edit Data Structure' : 'Create New Data Structure'}
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
          componentLabel="Output Parser"
        />
      </div>
    
  );
}

export default DataStructuresPage; 