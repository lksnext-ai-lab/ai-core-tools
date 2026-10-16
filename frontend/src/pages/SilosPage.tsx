import { useState, useEffect } from 'react';
import { Link, useParams, useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { Upload, Database, Gamepad2, ArrowDownToLine, Pencil, Trash2 } from 'lucide-react';
import { apiService } from '../services/api';
import ActionDropdown from '../components/ui/ActionDropdown';
import Table from '../components/ui/Table';
import { useAppRole } from '../hooks/useAppRole';
import { AppRole } from '../types/roles';
import ReadOnlyBanner from '../components/ui/ReadOnlyBanner';
import ImportModal, { type ConflictMode, type ImportResponse } from '../components/ui/ImportModal';
import { useConfirm } from '../contexts/ConfirmContext';
import { useApiMutation } from '../hooks/useApiMutation';
import { MESSAGES, errorMessage } from '../constants/messages';
import Title from '../components/ui/Title';
import ButtonApp from '../components/ui/ButtonApp';
import Alert from '../components/ui/Alert';
import ButtonLink from '../components/ui/ButtonLink';
import CardApp from '../components/ui/CardApp';
import BackgroundImage from '../components/ui/BackgroundImage';
import { LoadingState } from '../components/ui/LoadingState';

// ...existing code...
interface Silo {
  silo_id: number;
  name: string;
  description?: string;
  type?: string;
  created_at?: string;
  docs_count: number;
  vector_db_type?: string;
}

function SilosPage() {
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
  const [availableEmbeddingServices, setAvailableEmbeddingServices] = useState<Array<{ id: number; name: string }>>([]);
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
      setError(err instanceof Error ? err.message : 'Failed to load silos');
      console.error('Error loading silos:', err);
    } finally {
      setLoading(false);
    }
  }

  async function handleDelete(siloId: number) {
    if (!appId) return;

    const target = silos.find((s) => s.silo_id === siloId);
    const ok = await confirm({
      title: MESSAGES.CONFIRM_DELETE_TITLE('silo'),
      message: target
        ? `Are you sure you want to delete "${target.name}"? This action cannot be undone and removes all stored vectors.`
        : MESSAGES.CONFIRM_DELETE_MESSAGE('silo'),
      variant: 'danger',
      confirmLabel: 'Delete',
    });
    if (!ok) return;

    const result = await mutate(
      () => apiService.deleteSilo(Number.parseInt(appId), siloId),
      {
        loading: MESSAGES.DELETING('silo'),
        success: MESSAGES.DELETED('silo'),
        error: (err) => errorMessage(err, MESSAGES.DELETE_FAILED('silo')),
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

      toast.warning(
        'Silo exported successfully. Note: Vector data excluded. Re-upload documents after import.',
        { duration: 7000 },
      );
    } catch (err) {
      toast.error(errorMessage(err, MESSAGES.EXPORT_FAILED('silo')));
      console.error('Error exporting silo:', err);
    }
  }

  async function handleImport(
    file: File,
    conflictMode: ConflictMode,
    newName?: string
  ): Promise<ImportResponse> {
    if (!appId) {
      throw new Error('App ID is required');
    }

    try {
      // Parse file to check if embedding service selection is needed
      if (!requiresEmbeddingServiceSelection) {
        const fileContent = await file.text();
        const fileData = JSON.parse(fileContent);
        
        // Check if embedding service is needed but not bundled
        if (fileData.silo?.embedding_service_name && !fileData.embedding_service) {
          // Fetch available embedding services
          const services = await apiService.getEmbeddingServices(Number.parseInt(appId));
          setAvailableEmbeddingServices(
            services.map((svc: any) => ({ id: svc.service_id, name: svc.name }))
          );
          setRequiresEmbeddingServiceSelection(true);
          
          return {
            success: false,
            message: 'Please select an embedding service to continue',
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
        toast.success(result.message || MESSAGES.IMPORTED('silo'));
        void loadSilos();

        // Reset embedding service selection state
        setRequiresEmbeddingServiceSelection(false);
        setSelectedEmbeddingServiceId(undefined);
      }

      return result;
    } catch (err: any) {
      return {
        success: false,
        message: err?.message || 'Import failed',
      };
    }
  } 

  if (loading) {
    return (
      <div className="space-y-6">
        {/* Page Header */}
        <div className="flex items-center justify-between">
          <Title variant='titSecundario' titulo='Silos' subtitulo='Vector storage and retrieval systems for semantic search'></Title>
        </div>

        <LoadingState variant="page" message="Loading silos..." />
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-6">
        {/* Page Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Silos</h1>
            <p className="text-gray-600">Vector storage and retrieval systems for semantic search</p>
          </div>
        </div>

        <Alert
          type="error"
          title="Error Loading Silos"
          message={(
            <>
              {error}
              <button type="button" onClick={() => loadSilos()} className="mt-2 block underline">
                Try again
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
        <Title variant='titSecundario' titulo='Silos' subtitulo='Vector storage and retrieval systems for semantic search'></Title>
        <div className="flex items-center space-x-3">
          {hasMinRole(AppRole.ADMINISTRATOR) && (
            <ButtonApp
              label='Import Silo'
              icon={<Upload className="w-4 h-4" />}
              onClick={() => setShowImportModal(true)}
              variant="secondary"
              size="medium"
            />
          )}
          {canEdit && (
            <ButtonLink
              to={`/apps/${appId}/silos/new`}
              label="Create Silo"
              variant="primary"
              size="medium"
              icon={<span aria-hidden="true">+</span>}
            />
          )}
        </div>
      </div>

      {!canEdit && <ReadOnlyBanner userRole={userRole} minRole={AppRole.EDITOR} />}

      {/* Silos List */}
      {silos.length === 0 ? (
        <CardApp className="p-8 text-center">
          
          <BackgroundImage variant="gris" icon="Database" size={44} className="mx-auto mb-4" />
          <h3 className="font-display text-[19px] font-normal tracking-[-0.02em] text-fg dark:text-fg-dark mb-[6px]">No Silos Yet</h3>
          <p className="text-fg-secondary dark:text-fg-secondary-dark text-[13.5px] mb-4">
            Create your first silo to start storing and searching documents with vector embeddings.
          </p>
          {canEdit && (
            <Link 
              to={`/apps/${appId}/silos/new`}
              className="mx-auto w-max rounded-md px-[15px] py-[9px] text-sm border border-transparent bg-ink dark:bg-ink-dark text-ink-on dark:text-ink-on-dark hover:bg-ink-hover dark:hover:bg-ink-hover-dark"
            >
              <span aria-hidden="true" className="mr-2">+</span>
              <span>Create Your First Silo</span>
            </Link>
          )}
        </CardApp>
      ) : (
        <Table
          data={silos}
          keyExtractor={(silo) => silo.silo_id.toString()}
          columns={[
            {
              header: 'Name',
              render: (silo) => (
                <div className="flex items-center">
                  <div className="flex-shrink-0 h-10 w-10">
                    <BackgroundImage variant="marron" icon="Database" size={28}
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
                  </div>
                </div>
              )
            },
            {
              header: 'Description',
              accessor: 'description',
              className: 'px-6 py-4 whitespace-nowrap text-xs text-fg-secondary dark:text-fg-secondary-dark'
            },
            {
              header: 'Type',
              render: (silo) => (
                <span className="inline-flex px-2 py-1 text-xs font-semibold rounded-full bg-gray-100 text-gray-800">
                  {silo.type || 'Custom'}
                </span>
              )
            },
            {
              header: 'Vector DB',
              accessor: 'vector_db_type',
              render: (silo) => silo.vector_db_type || 'Unknown',
              className: "text-xs text-fg-secondary dark:text-fg-secondary-dark"
            },
            {
              header: 'Documents',
              render: (silo) => `${silo.docs_count} documents`,
              className: 'text-xs text-fg-secondary dark:text-fg-secondary-dark'
            },
            {
              header: 'Created',
              render: (silo) => silo.created_at ? new Date(silo.created_at).toLocaleDateString() : 'N/A',
              className: 'text-xs text-fg-secondary dark:text-fg-secondary-dark'
            },
            {
              header: 'Actions',
              headerClassName: 'px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider',
              className: 'text-xs text-fg-secondary dark:text-fg-secondary-dark',
              render: (silo) => (
                <ActionDropdown
                  actions={[
                    {
                      label: 'Playground',
                      onClick: () => navigate(`/apps/${appId}/silos/${silo.silo_id}/playground`),
                      icon: <Gamepad2 className="w-4 h-4" />,
                      variant: 'warning'
                    },
                    {
                      label: 'Export',
                      onClick: () => { void handleExport(silo.silo_id); },
                      icon: <ArrowDownToLine className="w-4 h-4" />,
                      variant: 'primary' as const
                    },
                    ...(canEdit ? [
                      {
                        label: 'Edit',
                        onClick: () => navigate(`/apps/${appId}/silos/${silo.silo_id}`),
                        icon: <Pencil className="w-4 h-4" />,
                        variant: 'primary' as const
                      },
                      {
                        label: 'Delete',
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
          emptyIcon={<Database className="w-10 h-10 text-gray-300" />}
          emptyMessage="No Silos Yet"
          emptySubMessage="Create your first silo to start storing and searching documents with vector embeddings."
          loading={loading}
        />
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
        componentLabel="Silo"
        requiresEmbeddingServiceSelection={requiresEmbeddingServiceSelection}
        availableEmbeddingServices={availableEmbeddingServices}
        selectedEmbeddingServiceId={selectedEmbeddingServiceId}
        onEmbeddingServiceChange={setSelectedEmbeddingServiceId}
      />
    </div>
  );
}

export default SilosPage; 