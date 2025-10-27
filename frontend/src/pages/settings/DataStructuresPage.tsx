import { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import Modal from '../../components/ui/Modal';
import DataStructureForm from '../../components/forms/DataStructureForm';
import { apiService } from '../../services/api';
import ActionDropdown from '../../components/ui/ActionDropdown';
import { useSettingsCache } from '../../contexts/SettingsCacheContext';
import { useAppRole } from '../../hooks/useAppRole';
import ReadOnlyBanner from '../../components/ui/ReadOnlyBanner';

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
  const { isOwner, isAdmin, userRole } = useAppRole(appId);
  const [dataStructures, setDataStructures] = useState<DataStructure[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingStructure, setEditingStructure] = useState<any>(null);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [structureToDelete, setStructureToDelete] = useState<DataStructure | null>(null);

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
      const response = await apiService.getOutputParsers(parseInt(appId));
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
      const response = await apiService.getOutputParsers(parseInt(appId));
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

  function handleDelete(structure: DataStructure) {
    setStructureToDelete(structure);
    setShowDeleteModal(true);
  }

  async function confirmDeleteStructure() {
    if (!structureToDelete || !appId) return;

    try {
      await apiService.deleteOutputParser(parseInt(appId), structureToDelete.parser_id);
      const newDataStructures = dataStructures.filter(ds => ds.parser_id !== structureToDelete.parser_id);
      setDataStructures(newDataStructures);
      // Update cache
      settingsCache.setDataStructures(appId, newDataStructures);
      setShowDeleteModal(false);
      setStructureToDelete(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete data structure');
      console.error('Error deleting data structure:', err);
    }
  }

  async function handleCreateStructure() {
    if (!appId) return;
    
    try {
      // Load a blank structure with available parsers list
      const blankStructure = await apiService.getOutputParser(parseInt(appId), 0);
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
      const structure = await apiService.getOutputParser(parseInt(appId), parserId);
      setEditingStructure(structure);
      setIsModalOpen(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load data structure details');
      console.error('Error loading data structure:', err);
    }
  }

  async function handleSaveStructure(data: any) {
    if (!appId) return;

    try {
      if (editingStructure && editingStructure.parser_id !== 0) {
        // Update existing structure - no need to invalidate cache
        await apiService.updateOutputParser(parseInt(appId), editingStructure.parser_id, data);
        await loadDataStructures();
      } else {
        // Create new structure - invalidate cache and force reload
        await apiService.createOutputParser(parseInt(appId), data);
        settingsCache.invalidateDataStructures(appId);
        await forceReloadDataStructures();
      }
      
      setIsModalOpen(false);
      setEditingStructure(null);
    } catch (err) {
      throw new Error(err instanceof Error ? err.message : 'Failed to save data structure');
    }
  }

  function handleCloseModal() {
    setIsModalOpen(false);
    setEditingStructure(null);
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
          <div className="bg-red-50 border border-red-200 rounded-lg p-4">
            <p className="text-red-600">Error: {error}</p>
            <button 
              onClick={() => loadDataStructures()}
              className="mt-2 text-red-800 hover:text-red-900 underline"
            >
              Try again
            </button>
          </div>
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
          {isAdmin && (
            <button 
              onClick={handleCreateStructure}
              className="bg-purple-600 hover:bg-purple-700 text-white px-4 py-2 rounded-lg flex items-center"
            >
              <span className="mr-2">+</span>
              Create Data Structure
            </button>
          )}
        </div>
        
        {/* Read-only banner for non-admins */}
        {!isAdmin && <ReadOnlyBanner userRole={userRole} />}

        {/* Data Structures Table */}
        {dataStructures.length > 0 ? (
          <div className="bg-white shadow rounded-lg overflow-visible">
            <div className="overflow-x-auto overflow-visible">
              <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Name
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Description
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Fields
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Created
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {dataStructures.map((structure) => (
                  <tr key={structure.parser_id} className="hover:bg-gray-50">
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div className="flex items-center">
                        <span className="text-purple-400 text-xl mr-3">📊</span>
                        <div>
                          <div className="text-sm font-medium text-gray-900">{structure.name}</div>
                        </div>
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      <div className="text-sm text-gray-900 max-w-xs truncate">
                        {structure.description || 'No description'}
                      </div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <span className={`inline-flex px-2 py-1 text-xs font-semibold rounded-full ${getFieldCountBadge(structure.field_count)}`}>
                        {structure.field_count} field{structure.field_count !== 1 ? 's' : ''}
                      </span>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                      {structure.created_at ? new Date(structure.created_at).toLocaleDateString() : 'N/A'}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm font-medium">
                      {isAdmin ? (
                        <ActionDropdown
                          actions={[
                            {
                              label: 'Edit',
                              onClick: () => handleEditStructure(structure.parser_id),
                              icon: '✏️',
                              variant: 'primary'
                            },
                            {
                              label: 'Delete',
                              onClick: () => handleDelete(structure),
                              icon: '🗑️',
                              variant: 'danger'
                            }
                          ]}
                          size="sm"
                        />
                      ) : (
                        <span className="text-gray-400 text-sm">View only</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
              </table>
            </div>
          </div>
        ) : (
          <div className="text-center py-12">
            <div className="text-6xl mb-4">📊</div>
            <h3 className="text-lg font-semibold text-gray-900 mb-2">No Data Structures</h3>
            <p className="text-gray-600 mb-6">
              Create your first data structure to define schemas for structured data extraction.
            </p>
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
                <span className="text-purple-400 text-xl">💡</span>
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
                <span className="text-blue-400 text-xl">📝</span>
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

        {/* Delete Confirmation Modal */}
        <Modal
          isOpen={showDeleteModal}
          onClose={() => {
            setShowDeleteModal(false);
            setStructureToDelete(null);
          }}
          title="Delete Data Structure"
        >
          <div className="p-6">
            <p className="text-gray-700 mb-6">
              Are you sure you want to delete "{structureToDelete?.name}"? This action cannot be undone.
            </p>
            <div className="flex justify-end gap-3">
              <button
                onClick={() => {
                  setShowDeleteModal(false);
                  setStructureToDelete(null);
                }}
                className="px-4 py-2 text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={confirmDeleteStructure}
                className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg transition-colors"
              >
                Delete
              </button>
            </div>
          </div>
        </Modal>
      </div>
    
  );
}

export default DataStructuresPage; 