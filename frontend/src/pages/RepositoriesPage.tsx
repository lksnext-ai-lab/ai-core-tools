import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { FolderOpen, Gamepad2, Pencil, Plus, Trash2 } from 'lucide-react';
import { apiService } from '../services/api';
import ActionDropdown from '../components/ui/ActionDropdown';
import Table from '../components/ui/Table';
import { useAppRole } from '../hooks/useAppRole';
import { AppRole } from '../types/roles';
import ReadOnlyBanner from '../components/ui/ReadOnlyBanner';
import { useConfirm } from '../contexts/ConfirmContext';
import { useApiMutation } from '../hooks/useApiMutation';
import { MESSAGES, errorMessage } from '../constants/messages';
import Title from '../components/ui/Title';
import Alert from '../components/ui/Alert';
import ButtonApp from '../components/ui/ButtonApp';
import BackgroundImage from '../components/ui/BackgroundImage';
import { LoadingState } from '../components/ui/LoadingState';
import type { ServiceLifecycleWarning } from '../types/services';
import ServiceLifecycleAlert from '../components/services/ServiceLifecycleAlert';

interface Repository {
  repository_id: number;
  name: string;
  created_at: string;
  resource_count: number;
  lifecycle_warnings?: ServiceLifecycleWarning[];
}

const RepositoriesPage: React.FC = () => {
  const { appId } = useParams<{ appId: string }>();
  const { hasMinRole, userRole } = useAppRole(appId);
  const canEdit = hasMinRole(AppRole.EDITOR);
  const confirm = useConfirm();
  const mutate = useApiMutation();

  const navigate = useNavigate();
  const [repositories, setRepositories] = useState<Repository[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (appId) {
      void loadRepositories();
    }
  }, [appId]);

  const loadRepositories = async () => {
    try {
      setLoading(true);
      const data = await apiService.getRepositories(Number.parseInt(appId!));
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

  const handleDeleteRepository = async (repository: Repository) => {
    const ok = await confirm({
      title: MESSAGES.CONFIRM_DELETE_TITLE('repository'),
      message: `Are you sure you want to delete "${repository.name}"? This action cannot be undone and will remove all associated documents.`,
      variant: 'danger',
      confirmLabel: 'Delete',
    });
    if (!ok) return;

    const result = await mutate(
      () => apiService.deleteRepository(Number.parseInt(appId!), repository.repository_id),
      {
        loading: MESSAGES.DELETING('repository'),
        success: MESSAGES.DELETED('repository'),
        error: (err) => errorMessage(err, MESSAGES.DELETE_FAILED('repository')),
      },
    );
    if (result === undefined) return;

    setRepositories(repositories.filter((r) => r.repository_id !== repository.repository_id));
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString();
  };

  if (loading) {
    return (
      <div className="space-y-6">
        {/* Page Header */}
        <div className="flex items-center justify-between">
          <Title variant="titSecundario" titulo="Repositories" subtitulo="Manage your document repositories" />
        </div>

        <LoadingState variant="page" message="Loading repositories..." />
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-6">
        {/* Page Header */}
        <div className="flex items-center justify-between">
          <Title variant="titSecundario" titulo="Repositories" subtitulo="Manage your document repositories" />
        </div>

        <Alert
          type="error"
          title="Error Loading Repositories"
          message={(
            <>
              {error}
              <button
                type="button"
                onClick={() => loadRepositories()}
                className="mt-2 block text-sm underline"
              >
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
        <Title variant="titSecundario" titulo="Repositories" subtitulo="Manage your document repositories" />
        {canEdit && (
          <ButtonApp
            label="Create Repository"
            onClick={handleCreateRepository}
            icon={<Plus className="w-4 h-4" aria-hidden="true" />}
            variant="primary"
            size="medium"
          />
        )}
      </div>

      {!canEdit && <ReadOnlyBanner userRole={userRole} minRole={AppRole.EDITOR} />}

      {/* Repositories List */}
      <Table
        data={repositories}
        keyExtractor={(repository) => repository.repository_id.toString()}
        columns={[
          {
            header: 'Name',
            render: (repository) => (
              <button 
                type="button"
                className="flex items-center cursor-pointer hover:bg-gray-50 p-2 rounded-md transition-colors w-full text-left"
                onClick={() => handleManageResources(repository.repository_id)}
              >
                <BackgroundImage icon={FolderOpen} size={40} iconSize={20} variant="marron" />
                <div className="ml-4">
                  <div className="text-sm font-medium text-fg dark:text-fg-dark transition-colors">
                    {repository.name}
                  </div>
                  <ServiceLifecycleAlert warnings={repository.lifecycle_warnings} variant="compact" className="mt-0.5" />
                </div>
              </button>
            )
          },
          {
            header: 'Documents',
            render: (repository) => `${repository.resource_count} documents`,
            className: 'px-6 py-4 whitespace-nowrap text-xs text-fg dark:text-fg-dark'
          },
          {
            header: 'Created',
            render: (repository) => formatDate(repository.created_at),
            className: 'px-6 py-4 whitespace-nowrap text-xs text-fg-secondary dark:text-fg-secondary-dark'
          },
          {
            header: 'Actions',
            headerClassName: 'text-right tracking-wider',
            className: 'px-6 py-4 whitespace-nowrap text-right text-xs text-fg-secondary dark:text-fg-secondary-dark relative',
            render: (repository) => (
              <ActionDropdown
                actions={[
                  ...(canEdit ? [
                    {
                      label: 'Manage Resources',
                      onClick: () => navigate(`/apps/${appId}/repositories/${repository.repository_id}/detail`),
                      icon: <FolderOpen className="w-4 h-4" />,
                      variant: 'success' as const
                    }
                  ] : []),
                  {
                    label: 'Playground',
                    onClick: () => navigate(`/apps/${appId}/repositories/${repository.repository_id}/playground`),
                    icon: <Gamepad2 className="w-4 h-4" />,
                    variant: 'warning'
                  },
                  ...(canEdit ? [
                    {
                      label: 'Edit',
                      onClick: () => handleEditRepository(repository.repository_id),
                      icon: <Pencil className="w-4 h-4" />,
                      variant: 'primary' as const
                    },
                    {
                      label: 'Delete',
                      onClick: () => { void handleDeleteRepository(repository); },
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
        emptyIcon={<FolderOpen className="w-10 h-10 text-gray-300" />}
        emptyMessage="No Repositories Yet"
        emptySubMessage="Create your first repository to start organizing and searching documents."
        loading={loading}
      />


      {!loading && repositories.length === 0 && canEdit && (
        <div className="text-center py-6">
          <ButtonApp
            label="Create Your First Repository"
            onClick={handleCreateRepository}
            variant="primary"
            size="medium"
          />
        </div>
      )}
    </div>
  );
};

export default RepositoriesPage; 