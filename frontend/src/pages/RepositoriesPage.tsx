import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { apiService } from '../services/api';
import Modal from '../components/ui/Modal';
import ActionDropdown from '../components/ui/ActionDropdown';
import Table from '../components/ui/Table';

interface Repository {
  repository_id: number;
  name: string;
  created_at: string;
  resource_count: number;
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

  const handleManageResources = (repositoryId: number) => {
    navigate(`/apps/${appId}/repositories/${repositoryId}/detail`);
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
      <div className="space-y-6">
        {/* Page Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Repositories</h1>
            <p className="text-gray-600">Manage your document repositories</p>
          </div>
        </div>

        <div className="flex items-center justify-center py-12">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-green-600"></div>
          <span className="ml-2">Loading repositories...</span>
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
            <h1 className="text-2xl font-bold text-gray-900">Repositories</h1>
            <p className="text-gray-600">Manage your document repositories</p>
          </div>
        </div>

        <div className="bg-red-50 border border-red-200 rounded-lg p-4">
          <div className="flex">
            <span className="text-red-400 text-xl mr-3">⚠️</span>
            <div>
              <h3 className="text-sm font-medium text-red-800">Error Loading Repositories</h3>
              <p className="text-sm text-red-600 mt-1">{error}</p>
              <button 
                onClick={() => loadRepositories()}
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
          <h1 className="text-2xl font-bold text-gray-900">Repositories</h1>
          <p className="text-gray-600">Manage your document repositories</p>
        </div>
        <button
          onClick={handleCreateRepository}
          className="bg-green-600 hover:bg-green-700 text-white px-4 py-2 rounded-lg flex items-center"
        >
          <span className="mr-2">+</span>
          Create Repository
        </button>
      </div>

      {/* Repositories List */}
      <Table
        data={repositories}
        keyExtractor={(repository) => repository.repository_id.toString()}
        columns={[
          {
            header: 'Name',
            render: (repository) => (
              <div 
                className="flex items-center cursor-pointer hover:bg-gray-50 p-2 rounded-md transition-colors"
                onClick={() => handleManageResources(repository.repository_id)}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    handleManageResources(repository.repository_id);
                  }
                }}
              >
                <div className="flex-shrink-0 h-10 w-10">
                  <div className="h-10 w-10 rounded-lg bg-green-100 flex items-center justify-center">
                    <span className="text-green-600 text-lg">📁</span>
                  </div>
                </div>
                <div className="ml-4">
                  <div className="text-sm font-medium text-gray-900 hover:text-blue-600 transition-colors">
                    {repository.name}
                  </div>
                </div>
              </div>
            )
          },
          {
            header: 'Documents',
            render: (repository) => `${repository.resource_count} documents`,
            className: 'px-6 py-4 whitespace-nowrap text-sm text-gray-900'
          },
          {
            header: 'Created',
            render: (repository) => formatDate(repository.created_at),
            className: 'px-6 py-4 whitespace-nowrap text-sm text-gray-500'
          },
          {
            header: 'Actions',
            headerClassName: 'px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider',
            className: 'px-6 py-4 whitespace-nowrap text-right text-sm font-medium relative',
            render: (repository) => (
              <ActionDropdown
                actions={[
                  {
                    label: 'Manage Resources',
                    onClick: () => navigate(`/apps/${appId}/repositories/${repository.repository_id}/detail`),
                    icon: '📁',
                    variant: 'success'
                  },
                  {
                    label: 'Playground',
                    onClick: () => navigate(`/apps/${appId}/repositories/${repository.repository_id}/playground`),
                    icon: '🎮',
                    variant: 'warning'
                  },
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
                size="sm"
              />
            )
          }
        ]}
        emptyIcon="📁"
        emptyMessage="No Repositories Yet"
        emptySubMessage="Create your first repository to start organizing and searching documents."
        loading={loading}
      />

      {!loading && repositories.length === 0 && (
        <div className="text-center py-6">
          <button
            onClick={handleCreateRepository}
            className="bg-green-600 hover:bg-green-700 text-white px-6 py-3 rounded-lg"
          >
            Create Your First Repository
          </button>
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