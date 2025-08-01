import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { apiService } from '../services/api';
import Modal from '../components/ui/Modal';
import ActionDropdown from '../components/ui/ActionDropdown';
import type { ActionItem } from '../components/ui/ActionDropdown';

interface Repository {
  repository_id: number;
  name: string;
  created_at: string;
  resource_count: number;
}

interface RepositoryDetail {
  repository_id: number;
  name: string;
  created_at: string;
  resources: Array<{
    resource_id: number;
    name: string;
    file_type: string;
    created_at: string;
  }>;
  embedding_services: Array<{
    service_id: number;
    name: string;
  }>;
}

const RepositoriesPage: React.FC = () => {
  const { appId } = useParams<{ appId: string }>();
  const navigate = useNavigate();
  const [repositories, setRepositories] = useState<Repository[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [repositoryToDelete, setRepositoryToDelete] = useState<Repository | null>(null);

  useEffect(() => {
    if (appId) {
      loadRepositories();
    }
  }, [appId]);

  const loadRepositories = async () => {
    try {
      setLoading(true);
      const data = await apiService.getRepositories(parseInt(appId!));
      setRepositories(data);
      setError(null);
    } catch (err) {
      console.error('Error loading repositories:', err);
      setError('Failed to load repositories');
    } finally {
      setLoading(false);
    }
  };

  const handleCreateRepository = () => {
    navigate(`/apps/${appId}/repositories/0`);
  };

  const handleEditRepository = (repositoryId: number) => {
    navigate(`/apps/${appId}/repositories/${repositoryId}`);
  };

  const handleDeleteRepository = (repository: Repository) => {
    setRepositoryToDelete(repository);
    setShowDeleteModal(true);
  };

  const confirmDeleteRepository = async () => {
    if (!repositoryToDelete) return;

    try {
      await apiService.deleteRepository(parseInt(appId!), repositoryToDelete.repository_id);
      setRepositories(repositories.filter(r => r.repository_id !== repositoryToDelete.repository_id));
      setShowDeleteModal(false);
      setRepositoryToDelete(null);
    } catch (err) {
      console.error('Error deleting repository:', err);
      setError('Failed to delete repository');
    }
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString();
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  return (
    <div className="container mx-auto px-4 py-8">
      {/* Header */}
      <div className="flex justify-between items-center mb-8">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Repositories</h1>
          <p className="text-gray-600 mt-2">Manage your document repositories</p>
        </div>
        <button
          onClick={handleCreateRepository}
          className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg flex items-center gap-2 transition-colors"
        >
          <span className="text-lg">+</span>
          New Repository
        </button>
      </div>

      {/* Error Message */}
      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg mb-6">
          {error}
        </div>
      )}

      {/* Repositories Grid */}
      {repositories.length === 0 ? (
        <div className="text-center py-12">
          <div className="text-6xl text-gray-400 mb-4">📁</div>
          <h3 className="text-lg font-medium text-gray-900 mb-2">No repositories yet</h3>
          <p className="text-gray-600 mb-6">Create your first repository to start organizing documents</p>
          <button
            onClick={handleCreateRepository}
            className="bg-blue-600 hover:bg-blue-700 text-white px-6 py-3 rounded-lg flex items-center gap-2 mx-auto transition-colors"
          >
            <span className="text-lg">+</span>
            Create Repository
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {repositories.map((repository) => (
            <div
              key={repository.repository_id}
              className="bg-white border border-gray-200 rounded-lg p-6 hover:shadow-md transition-shadow"
            >
              {/* Repository Header */}
              <div className="flex items-start justify-between mb-4">
                <div className="flex items-center gap-3">
                  <div className="bg-blue-100 p-2 rounded-lg">
                    <span className="text-blue-600 text-lg">📁</span>
                  </div>
                  <div>
                    <h3 className="font-semibold text-gray-900 truncate">{repository.name}</h3>
                    <p className="text-sm text-gray-500">
                      {repository.resource_count} {repository.resource_count === 1 ? 'document' : 'documents'}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-1">
                  <ActionDropdown
                    actions={[
                      {
                        label: 'Edit',
                        onClick: () => handleEditRepository(repository.repository_id),
                        icon: '✏️',
                        variant: 'primary'
                      },
                      {
                        label: 'Delete',
                        onClick: () => handleDeleteRepository(repository),
                        icon: '🗑️',
                        variant: 'danger'
                      }
                    ]}
                    triggerIcon="⚙️"
                    triggerText=""
                    size="sm"
                  />
                </div>
              </div>

              {/* Repository Details */}
              <div className="space-y-2 mb-4">
                <div className="flex items-center gap-2 text-sm text-gray-600">
                  <span>📅</span>
                  <span>Created {formatDate(repository.created_at)}</span>
                </div>
                <div className="flex items-center gap-2 text-sm text-gray-600">
                  <span>📄</span>
                  <span>{repository.resource_count} files</span>
                </div>
              </div>

              {/* Action Buttons */}
              <div className="flex gap-2">
                <button
                  onClick={() => navigate(`/apps/${appId}/repositories/${repository.repository_id}/detail`)}
                  className="flex-1 bg-gray-100 hover:bg-gray-200 text-gray-700 px-3 py-2 rounded-lg text-sm font-medium transition-colors"
                >
                  Manage
                </button>
                <button
                  onClick={() => navigate(`/apps/${appId}/repositories/${repository.repository_id}/playground`)}
                  className="flex-1 bg-blue-50 hover:bg-blue-100 text-blue-700 px-3 py-2 rounded-lg text-sm font-medium transition-colors"
                >
                  Search
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Delete Confirmation Modal */}
      <Modal
        isOpen={showDeleteModal}
        onClose={() => {
          setShowDeleteModal(false);
          setRepositoryToDelete(null);
        }}
        title="Delete Repository"
      >
        <div className="p-6">
          <p className="text-gray-700 mb-6">
            Are you sure you want to delete "{repositoryToDelete?.name}"? This action cannot be undone and will remove all associated documents.
          </p>
          <div className="flex justify-end gap-3">
            <button
              onClick={() => {
                setShowDeleteModal(false);
                setRepositoryToDelete(null);
              }}
              className="px-4 py-2 text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={confirmDeleteRepository}
              className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg transition-colors"
            >
              Delete
            </button>
          </div>
        </div>
      </Modal>
    </div>
  );
};

export default RepositoriesPage; 