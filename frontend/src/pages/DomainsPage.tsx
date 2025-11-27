import { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { apiService } from '../services/api';
import Modal from '../components/ui/Modal';
import ActionDropdown from '../components/ui/ActionDropdown';
import Alert from '../components/ui/Alert';
import Table from '../components/ui/Table';
import { useAppRole } from '../hooks/useAppRole';
import { AppRole } from '../types/roles';
import ReadOnlyBanner from '../components/ui/ReadOnlyBanner';

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
  
  const navigate = useNavigate();
  const [domains, setDomains] = useState<Domain[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [domainToDelete, setDomainToDelete] = useState<Domain | null>(null);

  useEffect(() => {
    loadDomains();
  }, [appId]);

  async function loadDomains() {
    if (!appId) return;
    
    try {
      setLoading(true);
      setError(null);
      const response = await apiService.getDomains(parseInt(appId));
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

    function handleDeleteDomain(domain: Domain) {
    setDomainToDelete(domain);
    setShowDeleteModal(true);
  }

  async function confirmDeleteDomain() {
    if (!domainToDelete || !appId) return;
    
    try {
      await apiService.deleteDomain(parseInt(appId), domainToDelete.domain_id);
      setDomains(domains.filter(d => d.domain_id !== domainToDelete.domain_id));
      setShowDeleteModal(false);
      setDomainToDelete(null);
    } catch (err) {
      console.error('Error deleting domain:', err);
      alert('Failed to delete domain');
    }
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
                    <span className="text-purple-600 text-lg">🌐</span>
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
                    icon: '🔗',
                    variant: 'warning'
                  },
                  ...(canEdit ? [
                    {
                      label: 'Edit',
                      onClick: () => navigate(`/apps/${appId}/domains/${domain.domain_id}`),
                      icon: '✏️',
                      variant: 'primary' as const
                    },
                    {
                      label: 'Delete',
                      onClick: () => handleDeleteDomain(domain),
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
        emptyIcon="🌐"
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

      {/* Delete Confirmation Modal */}
      <Modal
        isOpen={showDeleteModal}
        onClose={() => {
          setShowDeleteModal(false);
          setDomainToDelete(null);
        }}
        title="Delete Domain"
      >
        <div className="p-6">
          <p className="text-gray-700 mb-6">
            Are you sure you want to delete "{domainToDelete?.name}"? This action cannot be undone and will remove all associated URLs and indexed content.
          </p>
          <div className="flex justify-end gap-3">
            <button
              onClick={() => {
                setShowDeleteModal(false);
                setDomainToDelete(null);
              }}
              className="px-4 py-2 text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={confirmDeleteDomain}
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

export default DomainsPage; 