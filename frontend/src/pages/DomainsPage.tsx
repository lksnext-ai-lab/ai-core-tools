import { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Globe, Link2, Pencil, Plus, Trash2 } from 'lucide-react';
import { apiService } from '../services/api';
import ActionDropdown from '../components/ui/ActionDropdown';
import Alert from '../components/ui/Alert';
import Table from '../components/ui/Table';
import { useAppRole } from '../hooks/useAppRole';
import { AppRole } from '../types/roles';
import ReadOnlyBanner from '../components/ui/ReadOnlyBanner';
import { useConfirm } from '../contexts/ConfirmContext';
import { useApiMutation } from '../hooks/useApiMutation';
import { errorMessage } from '../constants/messages';
import { Title } from '../components/ui/Title';
import BackgroundImage from '../components/ui/BackgroundImage';
import { ButtonApp } from '../components/ui/ButtonApp';
import { LoadingState } from '../components/ui/LoadingState';

interface Domain {
  domain_id: number;
  name: string;
  description: string;
  base_url: string;
  created_at: string;
  url_count: number;
  silo_id?: number;
}

function DomainsPage() {
  const { appId } = useParams<{ appId: string }>();
  const { t, i18n } = useTranslation('common');
  const { hasMinRole, userRole } = useAppRole(appId);
  const canEdit = hasMinRole(AppRole.EDITOR);
  const confirm = useConfirm();
  const mutate = useApiMutation();

  const navigate = useNavigate();
  const [domains, setDomains] = useState<Domain[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void loadDomains();
  }, [appId]);

  async function loadDomains() {
    if (!appId) return;
    
    try {
      setLoading(true);
      setError(null);
      const response = await apiService.getDomains(Number.parseInt(appId));
      console.log('Domains API response:', response); // Debug log
      setDomains(response || []); // Response is the array directly, not response.data
    } catch (err) {
      console.error('Error loading domains:', err);
      setError(t('domainsPage.loadFailed'));
      setDomains([]); // Ensure domains is always an array
    } finally {
      setLoading(false);
    }
  }

  async function handleDeleteDomain(domain: Domain) {
    if (!appId) return;

    const ok = await confirm({
      title: t('domainsPage.confirmDeleteTitle'),
      message: t('domainsPage.confirmDeleteMessage', { name: domain.name }),
      variant: 'danger',
      confirmLabel: t('domainsPage.actions.delete'),
    });
    if (!ok) return;

    const result = await mutate(
      () => apiService.deleteDomain(Number.parseInt(appId), domain.domain_id),
      {
        loading: t('domainsPage.deleting'),
        success: t('domainsPage.deleted'),
        error: (err) => errorMessage(err, t('domainsPage.deleteFailed')),
      },
    );
    if (result === undefined) return;

    setDomains(domains.filter((d) => d.domain_id !== domain.domain_id));
  }

  if (loading) {
    return(
      <div className="space-y-6">
          {/* Page Header */}
          <div className="flex items-center justify-between">
            <Title variant="titSecundario" titulo={t('domainsPage.title')} subtitulo={t('domainsPage.subtitle')} titleMarginBottom={0} subtitleMarginBottom={0} />
          </div>

          <LoadingState variant="page" message={t('domainsPage.loading')} />
        </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-6">
        {/* Page Header */}
        <div className="flex items-center justify-between">
          <Title variant="titSecundario" titulo={t('domainsPage.title')} subtitulo={t('domainsPage.subtitle')} titleMarginBottom={0} subtitleMarginBottom={0} />
        </div>

        <Alert 
          type="error" 
          title={t('domainsPage.loadErrorTitle')}
          message={error}
          onDismiss={() => loadDomains()}
        />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <Title variant="titSecundario" titulo={t('domainsPage.title')} subtitulo={t('domainsPage.subtitle')} titleMarginBottom={0} subtitleMarginBottom={0} />
        {canEdit && (
          <ButtonApp
            label={t('domainsPage.actions.create')}
            variant="primary"
            size="medium"
            icon={<Plus className="w-4 h-4" />}
            onClick={() => navigate(`/apps/${appId}/domains/new`)}
          />
        )}
      </div>

            {!canEdit && <ReadOnlyBanner userRole={userRole} minRole={AppRole.EDITOR} />}

      {/* Domains List */}
      <Table
        data={domains || []}
        stickyEdgeColumns
        keyExtractor={(domain) => domain.domain_id.toString()}
        columns={[
          {
            header: t('domainsPage.columns.name'),
            render: (domain) => (
              <div className="flex items-center">
                <BackgroundImage icon={Globe} size={40} iconSize={20} variant="marron" />
                <div className="ml-4">
                  <div className="text-sm font-medium text-fg dark:text-fg-dark">
                    {canEdit ? (
                      <Link
                        to={`/apps/${appId}/domains/${domain.domain_id}`}
                        className="text-sm font-medium text-fg dark:text-fg-dark transition-colors"
                      >
                        {domain.name}
                      </Link>
                    ) : (
                      <span className="text-sm font-medium text-fg dark:text-fg-dark">
                        {domain.name}
                      </span>
                    )}
                  </div>
                  <div className="text-xs text-fg-secondary dark:text-fg-secondary-dark">{domain.description}</div>
                </div>
              </div>
            )
          },
          {
            header: t('domainsPage.columns.baseUrl'),
            accessor: 'base_url',
            className: 'px-6 py-4 whitespace-nowrap text-xs text-fg-secondary dark:text-fg-secondary-dark'
          },
          {
            header: t('domainsPage.columns.urls'),
            render: (domain) => t('domainsPage.urlCount', { count: domain.url_count }),
            className: 'px-6 py-4 whitespace-nowrap text-xs text-fg-secondary dark:text-fg-secondary-dark'
          },
          {
            header: t('domainsPage.columns.created'),
            render: (domain) => new Date(domain.created_at).toLocaleDateString(i18n.resolvedLanguage),
            className: 'px-6 py-4 whitespace-nowrap text-xs text-fg-secondary dark:text-fg-secondary-dark'
          },
          {
            header: t('domainsPage.columns.actions'),
            headerClassName: 'px-6 py-3 text-right  tracking-wider',
            className: 'px-6 py-4 whitespace-nowrap text-right text-sm font-medium relative',
            render: (domain) => (
              <ActionDropdown
                actions={[
                  {
                    label: t('domainsPage.actions.urls'),
                    onClick: () => navigate(`/apps/${appId}/domains/${domain.domain_id}/detail`),
                    icon: <Link2 className="w-4 h-4" />,
                    variant: 'warning'
                  },
                  ...(canEdit ? [
                    {
                      label: t('domainsPage.actions.edit'),
                      onClick: () => navigate(`/apps/${appId}/domains/${domain.domain_id}`),
                      icon: <Pencil className="w-4 h-4" />,
                      variant: 'primary' as const
                    },
                    {
                      label: t('domainsPage.actions.delete'),
                      onClick: () => { void handleDeleteDomain(domain); },
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
        emptyIcon={<BackgroundImage icon={Globe} size={64} iconSize={32} />}
        emptyMessage={t('domainsPage.emptyTitle')}
        emptySubMessage={t('domainsPage.emptyDescription')}
        loading={loading}
      />

      {!loading && (!domains || domains.length === 0) && canEdit && (
        <div className="text-center py-6">
          <ButtonApp
            label={t('domainsPage.actions.createFirst')}
            variant="primary"
            size="medium"
            onClick={() => navigate(`/apps/${appId}/domains/new`)}
          />
        </div>
      )}
    </div>
  );
}

export default DomainsPage; 