import { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { Globe, Link2, Pencil, Trash2 } from 'lucide-react';
import { apiService } from '../services/api';
import ActionDropdown from '../components/ui/ActionDropdown';
import Alert from '../components/ui/Alert';
import Table from '../components/ui/Table';
import { useAppRole } from '../hooks/useAppRole';
import { AppRole } from '../types/roles';
import ReadOnlyBanner from '../components/ui/ReadOnlyBanner';
import { useConfirm } from '../contexts/ConfirmContext';
import { useApiMutation } from '../hooks/useApiMutation';
import { MESSAGES, errorMessage } from '../constants/messages';

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
  const { hasMinRole, userRole } = useAppRole(appId);
  const canEdit = hasMinRole(AppRole.EDITOR);
  const confirm = useConfirm();
  const mutate = useApiMutation();

  const navigate = useNavigate();
  const [domains, setDomains] = useState<Domain[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadDomains();
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
      setError('Failed to load domains');
      setDomains([]); // Ensure domains is always an array
    } finally {
      setLoading(false);
    }
  }

  async function handleDeleteDomain(domain: Domain) {
    if (!appId) return;

    const ok = await confirm({
      title: MESSAGES.CONFIRM_DELETE_TITLE('domain'),
      message: `Are you sure you want to delete "${domain.name}"? This action cannot be undone and will remove all associated URLs and indexed content.`,
      variant: 'danger',
      confirmLabel: 'Delete',
    });
    if (!ok) return;

    const result = await mutate(
      () => apiService.deleteDomain(Number.parseInt(appId), domain.domain_id),
      {
        loading: MESSAGES.DELETING('domain'),
        success: MESSAGES.DELETED('domain'),
        error: (err) => errorMessage(err, MESSAGES.DELETE_FAILED('domain')),
      },
    );
    if (result === undefined) return;

    setDomains(domains.filter((d) => d.domain_id !== domain.domain_id));
  }

  if (loading) {
    return (
      <div className="space-y-6">
        {/* Page Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Domains</h1>
            <p className="text-gray-600">Web scraping domains for content extraction</p>
          </div>
        </div>

        <div className="flex items-center justify-center py-12">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-purple-600"></div>
          <span className="ml-2">Loading domains...</span>
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
            <h1 className="text-2xl font-bold text-gray-900">Domains</h1>
            <p className="text-gray-600">Web scraping domains for content extraction</p>
          </div>
        </div>

        <Alert 
          type="error" 
          title="Error Loading Domains" 
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
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Domains</h1>
          <p className="text-gray-600">Web scraping domains for content extraction</p>
        </div>
        {canEdit && (
          <button
            onClick={() => navigate(`/apps/${appId}/domains/new`)}
            className="bg-purple-600 hover:bg-purple-700 text-white px-4 py-2 rounded-lg flex items-center"
          >
            <span className="mr-2">+</span>
            {' '}Create Domain
          </button>
        )}
      </div>

            {!canEdit && <ReadOnlyBanner userRole={userRole} minRole={AppRole.EDITOR} />}

      {/* Domains List */}
      <Table
        data={domains || []}
        keyExtractor={(domain) => domain.domain_id.toString()}
        columns={[
          {
            header: 'Name',
            render: (domain) => (
              <div className="flex items-center">
                <div className="flex-shrink-0 h-10 w-10">
                  <div className="h-10 w-10 rounded-lg bg-purple-100 flex items-center justify-center">
                    <Globe className="w-5 h-5 text-purple-600" />
                  </div>
                </div>
                <div className="ml-4">
                  <div className="text-sm font-medium text-gray-900">
                    {canEdit ? (
                      <Link
                        to={`/apps/${appId}/domains/${domain.domain_id}`}
                        className="text-sm font-medium text-gray-900 hover:text-blue-600 transition-colors"
                      >
                        {domain.name}
                      </Link>
                    ) : (
                      <span className="text-sm font-medium text-gray-900">
                        {domain.name}
                      </span>
                    )}
                  </div>
                  <div className="text-sm text-gray-500">{domain.description}</div>
                </div>
              </div>
            )
          },
          {
            header: 'Base URL',
            accessor: 'base_url',
            className: 'px-6 py-4 whitespace-nowrap text-sm text-gray-900'
          },
          {
            header: 'URLs',
            render: (domain) => `${domain.url_count} URLs`,
            className: 'px-6 py-4 whitespace-nowrap text-sm text-gray-900'
          },
          {
            header: 'Created',
            render: (domain) => new Date(domain.created_at).toLocaleDateString(),
            className: 'px-6 py-4 whitespace-nowrap text-sm text-gray-500'
          },
          {
            header: 'Actions',
            headerClassName: 'px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider',
            className: 'px-6 py-4 whitespace-nowrap text-right text-sm font-medium relative',
            render: (domain) => (
              <ActionDropdown
                actions={[
                  {
                    label: 'URLs',
                    onClick: () => navigate(`/apps/${appId}/domains/${domain.domain_id}/detail`),
                    icon: <Link2 className="w-4 h-4" />,
                    variant: 'warning'
                  },
                  ...(canEdit ? [
                    {
                      label: 'Edit',
                      onClick: () => navigate(`/apps/${appId}/domains/${domain.domain_id}`),
                      icon: <Pencil className="w-4 h-4" />,
                      variant: 'primary' as const
                    },
                    {
                      label: 'Delete',
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
        emptyIcon={<Globe className="w-10 h-10 text-gray-300" />}
        emptyMessage="No Domains Yet"
        emptySubMessage="Create your first domain to start extracting content from websites."
        loading={loading}
      />

      {!loading && (!domains || domains.length === 0) && canEdit && (
        <div className="text-center py-6">
          <button
            onClick={() => navigate(`/apps/${appId}/domains/new`)}
            className="bg-purple-600 hover:bg-purple-700 text-white px-6 py-3 rounded-lg"
          >
            Create Your First Domain
          </button>
        </div>
      )}
    </div>
  );
}

export default DomainsPage; 