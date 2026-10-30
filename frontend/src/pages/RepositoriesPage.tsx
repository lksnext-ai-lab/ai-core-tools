import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { FolderOpen, Gamepad2, Pencil, Plus, Trash2 } from 'lucide-react';
import { apiService } from '../services/api';
import ActionDropdown from '../components/ui/ActionDropdown';
import Table from '../components/ui/Table';
import { useAppRole } from '../hooks/useAppRole';
import { AppRole } from '../types/roles';
import ReadOnlyBanner from '../components/ui/ReadOnlyBanner';
import { useConfirm } from '../contexts/ConfirmContext';
import { useApiMutation } from '../hooks/useApiMutation';
import { errorMessage } from '../constants/messages';
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
  const { t, i18n } = useTranslation('common');

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
      setError(t('repositoriesPage.loadFailed'));
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
      title: t('repositoriesPage.confirmDeleteTitle'),
      message: t('repositoriesPage.confirmDeleteMessage', { name: repository.name }),
      variant: 'danger',
      confirmLabel: t('repositoriesPage.actions.delete'),
    });
    if (!ok) return;

    const result = await mutate(
      () => apiService.deleteRepository(Number.parseInt(appId!), repository.repository_id),
      {
        loading: t('repositoriesPage.deleting'),
        success: t('repositoriesPage.deleted'),
        error: (err) => errorMessage(err, t('repositoriesPage.deleteFailed')),
      },
    );
    if (result === undefined) return;

    setRepositories(repositories.filter((r) => r.repository_id !== repository.repository_id));
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString(i18n.resolvedLanguage);
  };

  if (loading) {
    return (
      <div className="space-y-6">
        {/* Page Header */}
        <div className="flex items-center justify-between">
          <Title variant="titSecundario" titulo={t('repositoriesPage.title')} subtitulo={t('repositoriesPage.subtitle')} />
        </div>

        <LoadingState variant="page" message={t('repositoriesPage.loading')} />
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-6">
        {/* Page Header */}
        <div className="flex items-center justify-between">
          <Title variant="titSecundario" titulo={t('repositoriesPage.title')} subtitulo={t('repositoriesPage.subtitle')} />
        </div>

        <Alert
          type="error"
          title={t('repositoriesPage.loadErrorTitle')}
          message={(
            <>
              {error}
              <button
                type="button"
                onClick={() => loadRepositories()}
                className="mt-2 block text-sm underline"
              >
                {t('repositoriesPage.tryAgain')}
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
        <Title variant="titSecundario" titulo={t('repositoriesPage.title')} subtitulo={t('repositoriesPage.subtitle')} />
        {canEdit && (
          <ButtonApp
            label={t('repositoriesPage.actions.create')}
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
        stickyEdgeColumns
        keyExtractor={(repository) => repository.repository_id.toString()}
        columns={[
          {
            header: t('repositoriesPage.columns.name'),
            render: (repository) => (
              <button 
                type="button"
                className="flex items-center cursor-pointer  p-2 w-full text-left"
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
            header: t('repositoriesPage.columns.documents'),
            render: (repository) => t('repositoriesPage.documents', { count: repository.resource_count }),
            className: 'px-6 py-4 whitespace-nowrap text-xs text-fg-secondary dark:text-fg-secondary-dark'
          },
          {
            header: t('repositoriesPage.columns.created'),
            render: (repository) => formatDate(repository.created_at),
            className: 'px-6 py-4 whitespace-nowrap text-xs text-fg-secondary dark:text-fg-secondary-dark'
          },
          {
            header: t('repositoriesPage.columns.actions'),
            headerClassName: 'text-right tracking-wider',
            sticky: 'right',
            className: 'px-6 py-4 whitespace-nowrap text-right text-xs text-fg-secondary dark:text-fg-secondary-dark relative',
            render: (repository) => (
              <ActionDropdown
                actions={[
                  ...(canEdit ? [
                    {
                      label: t('repositoriesPage.actions.manageResources'),
                      onClick: () => navigate(`/apps/${appId}/repositories/${repository.repository_id}/detail`),
                      icon: <FolderOpen className="w-4 h-4" />,
                      variant: 'success' as const
                    }
                  ] : []),
                  {
                    label: t('repositoriesPage.actions.playground'),
                    onClick: () => navigate(`/apps/${appId}/repositories/${repository.repository_id}/playground`),
                    icon: <Gamepad2 className="w-4 h-4" />,
                    variant: 'warning'
                  },
                  ...(canEdit ? [
                    {
                      label: t('repositoriesPage.actions.edit'),
                      onClick: () => handleEditRepository(repository.repository_id),
                      icon: <Pencil className="w-4 h-4" />,
                      variant: 'primary' as const
                    },
                    {
                      label: t('repositoriesPage.actions.delete'),
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
        emptyIcon={<BackgroundImage icon={FolderOpen} size={64} iconSize={32} />}
        emptyMessage={t('repositoriesPage.emptyTitle')}
        emptySubMessage={t('repositoriesPage.emptyDescription')}
        loading={loading}
      />


      {!loading && repositories.length === 0 && canEdit && (
        <div className="text-center py-6">
          <ButtonApp
            label={t('repositoriesPage.actions.createFirst')}
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