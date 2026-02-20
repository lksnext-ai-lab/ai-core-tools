import { useState, useEffect } from 'react';
import { Link, useParams, useNavigate } from 'react-router-dom';
import { apiService } from '../services/api';
import ActionDropdown from '../components/ui/ActionDropdown';
import Table from '../components/ui/Table';
import { useAppRole } from '../hooks/useAppRole';
import { AppRole } from '../types/roles';
import ReadOnlyBanner from '../components/ui/ReadOnlyBanner';
import ImportModal, { type ConflictMode, type ImportResponse } from '../components/ui/ImportModal';
import Alert from '../components/ui/Alert';

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
  
  const [silos, setSilos] = useState<Silo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showImportModal, setShowImportModal] = useState(false);
  const [notification, setNotification] = useState<{ message: string; type: 'success' | 'error' | 'warning' } | null>(null);
  const [requiresEmbeddingServiceSelection, setRequiresEmbeddingServiceSelection] = useState(false);
  const [availableEmbeddingServices, setAvailableEmbeddingServices] = useState<Array<{ id: number; name: string }>>([]);
  const [selectedEmbeddingServiceId, setSelectedEmbeddingServiceId] = useState<number | undefined>(undefined);
  const navigate = useNavigate();

  // Load silos from the API
  useEffect(() => {
    loadSilos();
  }, [appId]);

  async function loadSilos() {
    if (!appId) return;
    
    try {
      setLoading(true);
      setError(null);
      const response = await apiService.getSilos(parseInt(appId));
      setSilos(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load silos');
      console.error('Error loading silos:', err);
    } finally {
      setLoading(false);
    }
  }

  async function handleDelete(siloId: number) {
    if (!confirm('Are you sure you want to delete this silo? This action cannot be undone.')) {
      return;
    }

    if (!appId) return;

    try {
      await apiService.deleteSilo(parseInt(appId), siloId);
      // Remove from local state
      setSilos(silos.filter(s => s.silo_id !== siloId));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete silo');
      console.error('Error deleting silo:', err);
    }
  }

  async function handleExport(siloId: number) {
    if (!appId) return;

    try {
      const silo = silos.find(s => s.silo_id === siloId);
      const siloName = silo?.name || 'silo';
      
      const blob = await apiService.exportSilo(parseInt(appId), siloId);
      
      // Generate filename
      const timestamp = new Date().toISOString().split('T')[0];
      const sanitizedName = siloName.replace(/[^a-z0-9]/gi, '_').toLowerCase();
      const filename = `silo-${sanitizedName}-${timestamp}.json`;
      
      // Download
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);

      // Show warning notification (7 seconds)
      setNotification({
        message: 'Silo exported successfully. Note: Vector data excluded. Re-upload documents after import.',
        type: 'warning'
      });
      setTimeout(() => setNotification(null), 7000);
    } catch (err) {
      setNotification({
        message: err instanceof Error ? err.message : 'Failed to export silo',
        type: 'error'
      });
      setTimeout(() => setNotification(null), 5000);
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
          const services = await apiService.getEmbeddingServices(parseInt(appId));
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
        parseInt(appId),
        file,
        conflictMode,
        newName,
        selectedEmbeddingServiceId
      );

      if (result.success) {
        setShowImportModal(false);
        setNotification({
          message: result.message || 'Silo imported successfully',
          type: 'success'
        });
        void loadSilos(); // Reload silos list
        setTimeout(() => setNotification(null), 5000);
        
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
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Silos</h1>
            <p className="text-gray-600">Vector storage and retrieval systems for semantic search</p>
          </div>
        </div>

        <div className="flex items-center justify-center py-12">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-yellow-600"></div>
          <span className="ml-2">Loading silos...</span>
        </div>
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

        <div className="bg-red-50 border border-red-200 rounded-lg p-4">
          <div className="flex">
            <span className="text-red-400 text-xl mr-3">⚠️</span>
            <div>
              <h3 className="text-sm font-medium text-red-800">Error Loading Silos</h3>
              <p className="text-sm text-red-600 mt-1">{error}</p>
              <button 
                onClick={() => loadSilos()}
                className="mt-2 text-sm text-red-800 hover:text-red-900 underline"
              >
                Try again
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Silos</h1>
          <p className="text-gray-600">Vector storage and retrieval systems for semantic search</p>
        </div>
        <div className="flex items-center space-x-3">
          {hasMinRole(AppRole.ADMINISTRATOR) && (
            <button
              onClick={() => setShowImportModal(true)}
              className="bg-green-600 hover:bg-green-700 text-white px-4 py-2 rounded-lg flex items-center"
            >
              <span aria-hidden="true" className="mr-2">⬆️</span>
              <span>Import Silo</span>
            </button>
          )}
          {canEdit && (
            <Link 
              to={`/apps/${appId}/silos/new`}
              className="bg-yellow-600 hover:bg-yellow-700 text-white px-4 py-2 rounded-lg flex items-center"
            >
              <span aria-hidden="true" className="mr-2">+</span>
              <span>Create Silo</span>
            </Link>
          )}
        </div>
      </div>

      {!canEdit && <ReadOnlyBanner userRole={userRole} minRole={AppRole.EDITOR} />}

      {/* Notification */}
      {notification && (
        <Alert
          type={notification.type}
          message={notification.message}
          onDismiss={() => setNotification(null)}
        />
      )}

      {/* Silos List */}
      {silos.length === 0 ? (
        <div className="bg-white rounded-lg shadow-md border p-8 text-center">
          <div className="text-6xl mb-4">🗄️</div>
          <h3 className="text-lg font-semibold text-gray-900 mb-2">No Silos Yet</h3>
          <p className="text-gray-600 mb-4">
            Create your first silo to start storing and searching documents with vector embeddings.
          </p>
          {canEdit && (
            <Link 
              to={`/apps/${appId}/silos/new`}
              className="bg-yellow-600 hover:bg-yellow-700 text-white px-6 py-2 rounded-lg inline-flex items-center"
            >
              <span aria-hidden="true" className="mr-2">+</span>
              <span>Create Your First Silo</span>
            </Link>
          )}
        </div>
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
                    <div className="h-10 w-10 rounded-lg bg-yellow-100 flex items-center justify-center">
                      <span className="text-yellow-600 text-lg">🗄️</span>
                    </div>
                  </div>
                  <div className="ml-4">
                    <div className="text-sm font-medium text-gray-900">
                      {canEdit ? (
                        <Link
                          to={`/apps/${appId}/silos/${silo.silo_id}`}
                          className="text-sm font-medium text-gray-900 hover:text-blue-600 transition-colors"
                        >
                          {silo.name}
                        </Link>
                      ) : (
                        <span className="text-sm font-medium text-gray-900">
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
              className: 'px-6 py-4 whitespace-nowrap text-sm text-gray-900'
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
              className: 'px-6 py-4 whitespace-nowrap text-sm text-gray-900'
            },
            {
              header: 'Documents',
              render: (silo) => `${silo.docs_count} documents`,
              className: 'px-6 py-4 whitespace-nowrap text-sm text-gray-900'
            },
            {
              header: 'Created',
              render: (silo) => silo.created_at ? new Date(silo.created_at).toLocaleDateString() : 'N/A',
              className: 'px-6 py-4 whitespace-nowrap text-sm text-gray-500'
            },
            {
              header: 'Actions',
              headerClassName: 'px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider',
              className: 'px-6 py-4 whitespace-nowrap text-right text-sm font-medium',
              render: (silo) => (
                <ActionDropdown
                  actions={[
                    {
                      label: 'Playground',
                      onClick: () => navigate(`/apps/${appId}/silos/${silo.silo_id}/playground`),
                      icon: '🎮',
                      variant: 'warning'
                    },
                    {
                      label: 'Export',
                      onClick: () => { void handleExport(silo.silo_id); },
                      icon: '⬇️',
                      variant: 'primary' as const
                    },
                    ...(canEdit ? [
                      {
                        label: 'Edit',
                        onClick: () => navigate(`/apps/${appId}/silos/${silo.silo_id}`),
                        icon: '✏️',
                        variant: 'primary' as const
                      },
                      {
                        label: 'Delete',
                        onClick: () => { void handleDelete(silo.silo_id); },
                        icon: '🗑️',
                        variant: 'danger' as const
                      }
                    ] : [])
                  ]}
                  size="sm"
                />
              )
            }
          ]}
          emptyIcon="🗄️"
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