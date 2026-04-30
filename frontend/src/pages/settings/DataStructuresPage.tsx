import { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { toast } from 'sonner';
import { BarChart2, Upload, ArrowDownToLine, Pencil, Trash2, Lightbulb, FileText } from 'lucide-react';
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
    loadDataStructures();
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

  const getFieldCountBadge = (count: number) => {
    if (count === 0) return 'bg-gray-100 text-gray-800';
    if (count <= 3) return 'bg-green-100 text-green-800';
    if (count <= 7) return 'bg-blue-100 text-blue-800';
    return 'bg-purple-100 text-purple-800';
  };

  if (loading) {
    return (
      
        <div className="p-6 text-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-purple-600 mx-auto"></div>
          <p className="mt-2 text-gray-600">Loading data structures...</p>
        </div>
      
    );
  }

  if (error) {
    return (
      <div className="p-6">
        <Alert type="error" message={error} onDismiss={() => loadDataStructures()} />
      </div>
    );
  }

  return (
    
      <div className="p-6">
        {/* Header */}
        <div className="flex justify-between items-center mb-6">
          <div>
            <h2 className="text-xl font-semibold text-gray-900">Data Structures</h2>
            <p className="text-gray-600">Define schemas for structured data extraction and validation</p>
          </div>
          {canEdit && (
            <div className="flex gap-2">
              <button
                onClick={() => setShowImportModal(true)}
                className="border border-gray-300 hover:bg-gray-50 text-gray-700 px-4 py-2 rounded-lg flex items-center"
              >
                <Upload className="w-4 h-4 mr-2" />Import
              </button>
              <button 
                onClick={handleCreateStructure}
                className="bg-purple-600 hover:bg-purple-700 text-white px-4 py-2 rounded-lg flex items-center"
              >
                <span className="mr-2">+</span>
                {' '}Create Data Structure
              </button>
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
                  <BarChart2 className="w-5 h-5 text-purple-400 mr-3 shrink-0" />
                  {canEdit ? (
                    <button
                      type="button"
                      className="text-sm font-medium text-gray-900 hover:text-blue-600 transition-colors text-left"
                      onClick={() => void handleEditStructure(structure.parser_id)}
                    >
                      {structure.name}
                    </button>
                  ) : (
                    <span className="text-sm font-medium text-gray-900">
                      {structure.name}
                    </span>
                  )}
                </div>
              )
            },
            {
              header: 'Description',
              render: (structure) => (
                <div className="text-sm text-gray-900 max-w-xs truncate">
                  {structure.description || 'No description'}
                </div>
              ),
              className: 'px-6 py-4'
            },
            {
              header: 'Fields',
              render: (structure) => (
                <span className={`inline-flex px-2 py-1 text-xs font-semibold rounded-full ${getFieldCountBadge(structure.field_count)}`}>
                  {structure.field_count} field{structure.field_count === 1 ? '' : 's'}
                </span>
              )
            },
            {
              header: 'Created',
              render: (structure) => structure.created_at ? new Date(structure.created_at).toLocaleDateString() : 'N/A',
              className: 'px-6 py-4 whitespace-nowrap text-sm text-gray-500'
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
                        icon: exportingParserId === structure.parser_id ? <ArrowDownToLine className="w-4 h-4 animate-pulse" /> : <ArrowDownToLine className="w-4 h-4" />,
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
            <button 
              onClick={handleCreateStructure}
              className="bg-purple-600 hover:bg-purple-700 text-white px-6 py-3 rounded-lg"
            >
              Create First Data Structure
            </button>
          </div>
        )}

        {/* Info Boxes */}
        <div className="mt-6 space-y-4">
          {/* Main Info */}
          <div className="bg-purple-50 border border-purple-200 rounded-lg p-4">
            <div className="flex">
              <div className="flex-shrink-0">
                <Lightbulb className="w-5 h-5 text-purple-400" />
              </div>
              <div className="ml-3">
                <h3 className="text-sm font-medium text-purple-800">
                  About Data Structures
                </h3>
                <div className="mt-2 text-sm text-purple-700">
                  <p>
                    Data structures are dynamic schemas that define the format for structured data extraction. 
                    They automatically generate Pydantic models for validation and can reference other structures 
                    for complex nested data patterns.
                  </p>
                </div>
              </div>
            </div>
          </div>

          {/* Examples */}
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
            <div className="flex">
              <div className="flex-shrink-0">
                <FileText className="w-5 h-5 text-blue-400" />
              </div>
              <div className="ml-3">
                <h3 className="text-sm font-medium text-blue-800">
                  Common Use Cases
                </h3>
                <div className="mt-2 text-sm text-blue-700">
                  <ul className="list-disc list-inside space-y-1">
                    <li><strong>Document Analysis:</strong> Extract structured metadata from documents</li>
                    <li><strong>Agent Responses:</strong> Ensure consistent output format from AI agents</li>
                    <li><strong>Data Validation:</strong> Validate and type-check extracted information</li>
                    <li><strong>API Integration:</strong> Define schemas for external data sources</li>
                    <li><strong>Complex Objects:</strong> Build nested structures with references</li>
                  </ul>
                </div>
              </div>
            </div>
          </div>
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