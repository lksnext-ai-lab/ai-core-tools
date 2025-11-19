import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { apiService } from '../services/api';
import Modal from '../components/ui/Modal';
import ActionDropdown from '../components/ui/ActionDropdown';
import type { ActionItem } from '../components/ui/ActionDropdown';
import Alert from '../components/ui/Alert';

interface URL {
  url_id: number;
  url: string;
  created_at: string;
  updated_at?: string;
  status?: string;
}

interface DomainDetail {
  domain_id: number;
  name: string;
  description: string;
  base_url: string;
  content_tag: string;
  content_class: string;
  content_id: string;
  created_at: string;
  url_count: number;
  silo_id?: number;
  embedding_service_id?: number;
  embedding_services: Array<{
    service_id: number;
    name: string;
  }>;
}

const DomainDetailPage: React.FC = () => {
  const { appId, domainId } = useParams<{ appId: string; domainId: string }>();
  const navigate = useNavigate();
  
  const [domain, setDomain] = useState<DomainDetail | null>(null);
  const [urls, setUrls] = useState<URL[]>([]);
  const [loading, setLoading] = useState(true);
  const [urlsLoading, setUrlsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  // Add URL modal
  const [showAddUrlModal, setShowAddUrlModal] = useState(false);
  const [newUrl, setNewUrl] = useState('');
  const [addingUrl, setAddingUrl] = useState(false);
  
  // Delete URL modal
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [urlToDelete, setUrlToDelete] = useState<URL | null>(null);
  const [deletingUrl, setDeletingUrl] = useState(false);
  
  // Unindex URL modal
  const [showUnindexModal, setShowUnindexModal] = useState(false);
  const [urlToUnindex, setUrlToUnindex] = useState<URL | null>(null);
  const [unindexingUrl, setUnindexingUrl] = useState(false);
  
  // Reject URL modal
  const [showRejectModal, setShowRejectModal] = useState(false);
  const [urlToReject, setUrlToReject] = useState<URL | null>(null);
  const [rejectingUrl, setRejectingUrl] = useState(false);
  
  // Content preview modal
  const [showContentModal, setShowContentModal] = useState(false);
  const [urlContent, setUrlContent] = useState<{url: string, content: string | null, message: string} | null>(null);
  const [loadingContent, setLoadingContent] = useState(false);
  
  // Reindex states
  const [reindexingUrls, setReindexingUrls] = useState<Set<number>>(new Set());
  const [reindexingDomain, setReindexingDomain] = useState(false);
  
  // Success/Error messages
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    if (appId && domainId) {
      loadDomain();
      loadUrls();
    }
  }, [appId, domainId]);

  const loadDomain = async () => {
    try {
      setLoading(true);
      const data = await apiService.getDomain(parseInt(appId!), parseInt(domainId!));
      setDomain(data);
      setError(null);
    } catch (err) {
      console.error('Error loading domain:', err);
      setError('Failed to load domain');
    } finally {
      setLoading(false);
    }
  };

  const loadUrls = async () => {
    try {
      setUrlsLoading(true);
      const data = await apiService.getDomainUrls(parseInt(appId!), parseInt(domainId!));
      setUrls(data || []);
    } catch (err) {
      console.error('Error loading URLs:', err);
      setError('Failed to load URLs');
    } finally {
      setUrlsLoading(false);
    }
  };

  const handleAddUrl = async () => {
    if (!newUrl.trim() || !appId || !domainId) return;
    
    try {
      setAddingUrl(true);
      await apiService.addUrlToDomain(parseInt(appId), parseInt(domainId), { url: newUrl.trim() });
      setNewUrl('');
      setShowAddUrlModal(false);
      await loadUrls(); // Reload URLs
    } catch (err) {
      console.error('Error adding URL:', err);
      alert('Failed to add URL');
    } finally {
      setAddingUrl(false);
    }
  };

  const handleDeleteUrl = (url: URL) => {
    setUrlToDelete(url);
    setShowDeleteModal(true);
  };

  const confirmDeleteUrl = async () => {
    if (!urlToDelete || !appId || !domainId) return;
    
    try {
      setDeletingUrl(true);
      await apiService.deleteUrlFromDomain(parseInt(appId), parseInt(domainId), urlToDelete.url_id);
      setUrls(urls.filter(u => u.url_id !== urlToDelete.url_id));
      setShowDeleteModal(false);
      setUrlToDelete(null);
      setSuccessMessage('URL deleted successfully');
      setTimeout(() => setSuccessMessage(null), 3000);
    } catch (err) {
      console.error('Error deleting URL:', err);
      setErrorMessage('Failed to delete URL');
      setTimeout(() => setErrorMessage(null), 3000);
    } finally {
      setDeletingUrl(false);
    }
  };

  const handleReindexUrl = async (urlId: number) => {
    if (!appId || !domainId) return;
    
    try {
      setReindexingUrls(prev => new Set(prev).add(urlId));
      const response = await apiService.reindexUrl(parseInt(appId), parseInt(domainId), urlId);
      await loadUrls(); // Reload to get updated timestamps
      
      // Show success message
      if (response.success) {
        setSuccessMessage(response.message || 'URL re-indexed successfully');
      } else {
        setErrorMessage(response.message || 'Failed to re-index URL');
      }
      setTimeout(() => {
        setSuccessMessage(null);
        setErrorMessage(null);
      }, 3000);
    } catch (err) {
      console.error('Error reindexing URL:', err);
      setErrorMessage('Failed to re-index URL');
      setTimeout(() => setErrorMessage(null), 3000);
    } finally {
      setReindexingUrls(prev => {
        const newSet = new Set(prev);
        newSet.delete(urlId);
        return newSet;
      });
    }
  };

  const handleUnindexUrl = async (url: URL) => {
    if (!appId || !domainId) return;
    
    setUrlToUnindex(url);
    setShowUnindexModal(true);
  };

  const confirmUnindexUrl = async () => {
    if (!urlToUnindex || !appId || !domainId) return;
    
    try {
      setUnindexingUrl(true);
      await apiService.unindexUrl(parseInt(appId), parseInt(domainId), urlToUnindex.url_id);
      await loadUrls(); // Reload to get updated status
      setShowUnindexModal(false);
      setUrlToUnindex(null);
      setSuccessMessage('URL unindexed successfully');
      setTimeout(() => setSuccessMessage(null), 3000);
    } catch (err) {
      console.error('Error unindexing URL:', err);
      setErrorMessage('Failed to unindex URL');
      setTimeout(() => setErrorMessage(null), 3000);
    } finally {
      setUnindexingUrl(false);
    }
  };

  const handleRejectUrl = async (url: URL) => {
    if (!appId || !domainId) return;
    
    setUrlToReject(url);
    setShowRejectModal(true);
  };

  const confirmRejectUrl = async () => {
    if (!urlToReject || !appId || !domainId) return;
    
    try {
      setRejectingUrl(true);
      await apiService.rejectUrl(parseInt(appId), parseInt(domainId), urlToReject.url_id);
      await loadUrls(); // Reload to get updated status
      setShowRejectModal(false);
      setUrlToReject(null);
      setSuccessMessage('URL rejected successfully');
      setTimeout(() => setSuccessMessage(null), 3000);
    } catch (err) {
      console.error('Error rejecting URL:', err);
      setErrorMessage('Failed to reject URL');
      setTimeout(() => setErrorMessage(null), 3000);
    } finally {
      setRejectingUrl(false);
    }
  };

  const handleReindexDomain = async () => {
    if (!appId || !domainId) return;
    
    try {
      setReindexingDomain(true);
      await apiService.reindexDomain(parseInt(appId), parseInt(domainId));
      await loadUrls(); // Reload to get updated timestamps
      
      // Show success message
      setSuccessMessage('Domain re-indexed successfully');
      setTimeout(() => setSuccessMessage(null), 3000);
    } catch (err) {
      console.error('Error reindexing domain:', err);
      setErrorMessage('Failed to re-index domain');
      setTimeout(() => setErrorMessage(null), 3000);
    } finally {
      setReindexingDomain(false);
    }
  };

  const handleViewContent = async (url: URL) => {
    if (!appId || !domainId) return;
    
    try {
      setLoadingContent(true);
      setShowContentModal(true);
      setUrlContent(null);
      
      const content = await apiService.getUrlContent(parseInt(appId), parseInt(domainId), url.url_id);
      setUrlContent(content);
    } catch (err) {
      console.error('Error loading content:', err);
      setUrlContent({
        url: domain ? domain.base_url + url.url : url.url,
        content: null,
        message: 'Failed to load content'
      });
    } finally {
      setLoadingContent(false);
    }
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  const getUrlStatus = (url: URL) => {
    if (reindexingUrls.has(url.url_id)) {
      return {
        text: 'Indexing...',
        badge: 'bg-blue-100 text-blue-800',
        icon: '⏳'
      };
    }
    
    switch (url.status) {
      case 'indexed':
        return {
          text: 'Indexed',
          badge: 'bg-green-100 text-green-800',
          icon: '✅'
        };
      case 'indexing':
        return {
          text: 'Indexing',
          badge: 'bg-blue-100 text-blue-800',
          icon: '⏳'
        };
      case 'rejected':
        return {
          text: 'Rejected',
          badge: 'bg-red-100 text-red-800',
          icon: '❌'
        };
      case 'unindexed':
        return {
          text: 'Unindexed',
          badge: 'bg-gray-100 text-gray-600',
          icon: '🚫'
        };
      case 'pending':
        return {
          text: 'Pending',
          badge: 'bg-yellow-100 text-yellow-800',
          icon: '⏸️'
        };
      default:
        return {
          text: 'Not Indexed',
          badge: 'bg-gray-100 text-gray-800',
          icon: '⚪'
        };
    }
  };

  return (
    <div className="p-6">
      {/* Success Message */}
      {successMessage && <Alert type="success" message={successMessage} onDismiss={() => setSuccessMessage(null)} className="mb-6" />}

      {/* Error Message */}
      {errorMessage && <Alert type="error" message={errorMessage} onDismiss={() => setErrorMessage(null)} className="mb-6" />}

      {loading ? (
        <div className="container mx-auto px-4 py-8">
          <div className="flex justify-center items-center h-64">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
          </div>
        </div>
      ) : error || !domain ? (
        <div className="container mx-auto px-4 py-8">
          <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg mb-6">
            <p className="font-medium">Error</p>
            <p>{error || 'Domain not found'}</p>
          </div>
          <button
            onClick={() => navigate(`/apps/${appId}`)}
            className="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700"
          >
            Back to App
          </button>
        </div>
      ) : (
        <div className="container mx-auto px-4 py-8">
          {/* Header */}
          <div className="flex justify-between items-center mb-6">
            <div>
              <h1 className="text-2xl font-bold text-gray-900">{domain.name}</h1>
              <p className="text-gray-600">{domain.description}</p>
            </div>
            <button
              onClick={() => navigate(`/apps/${appId}/domains`)}
              className="bg-gray-600 text-white px-4 py-2 rounded-lg hover:bg-gray-700"
            >
              Back to Domains
            </button>
          </div>

          {/* Scraping Configuration */}
          <div className="bg-white border border-gray-200 rounded-lg p-6 mb-6">
            <h2 className="text-xl font-semibold text-gray-900 mb-4">Scraping Configuration</h2>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div>
                <span className="text-sm font-medium text-gray-500">Content Tag:</span>
                <p className="text-gray-900">{domain.content_tag || 'body'}</p>
              </div>
              <div>
                <span className="text-sm font-medium text-gray-500">Content Class:</span>
                <p className="text-gray-900">{domain.content_class || 'None'}</p>
              </div>
              <div>
                <span className="text-sm font-medium text-gray-500">Content ID:</span>
                <p className="text-gray-900">{domain.content_id || 'None'}</p>
              </div>
            </div>
          </div>

          {/* URLs Section */}
          <div className="bg-white border border-gray-200 rounded-lg">
            <div className="px-6 py-4 border-b border-gray-200 flex justify-between items-center">
              <h2 className="text-xl font-semibold text-gray-900">URLs ({urls.length})</h2>
              {urls.length > 0 && (
                <button
                  onClick={() => setShowAddUrlModal(true)}
                  className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg flex items-center"
                >
                  <span className="mr-2">+</span>
                  Add URL
                </button>
              )}
            </div>
            
            {urlsLoading ? (
              <div className="flex justify-center items-center py-8">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
              </div>
            ) : urls.length === 0 ? (
              <div className="text-center py-12">
                <div className="text-gray-400 text-6xl mb-4">🔗</div>
                <h3 className="text-lg font-medium text-gray-900 mb-2">No URLs yet</h3>
                <p className="text-gray-500 mb-6">Add your first URL to start indexing content</p>
                <button
                  onClick={() => setShowAddUrlModal(true)}
                  className="bg-blue-600 hover:bg-blue-700 text-white px-6 py-3 rounded-lg"
                >
                  Add First URL
                </button>
              </div>
            ) : (
              <div className="overflow-x-auto overflow-visible">
                <table className="min-w-full divide-y divide-gray-200">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                        URL
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                        Status
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                        Added
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                        Last Indexed
                      </th>
                      <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                        Actions
                      </th>
                    </tr>
                  </thead>
                  <tbody className="bg-white divide-y divide-gray-200">
                    {urls.map((url) => {
                      const status = getUrlStatus(url);
                      return (
                        <tr key={url.url_id} className="hover:bg-gray-50">
                          <td className="px-6 py-4 whitespace-nowrap">
                            <div className="text-sm text-gray-900 max-w-md truncate">
                              {domain.base_url}{url.url}
                            </div>
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap">
                            <span className={`inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium ${status.badge}`}>
                              <span>{status.icon}</span>
                              {status.text}
                            </span>
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                            {formatDate(url.created_at)}
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                            {url.updated_at ? formatDate(url.updated_at) : 'Never'}
                          </td>
                        <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                          <ActionDropdown
                            actions={[
                              {
                                label: 'View Content',
                                onClick: () => handleViewContent(url),
                                icon: '👁️',
                                variant: 'success'
                              },
                              {
                                label: 'Reindex URL',
                                onClick: () => handleReindexUrl(url.url_id),
                                icon: reindexingUrls.has(url.url_id) ? '⏳' : '🔄',
                                variant: 'primary',
                                disabled: reindexingUrls.has(url.url_id)
                              },
                              {
                                label: 'Unindex URL',
                                onClick: () => handleUnindexUrl(url),
                                icon: reindexingUrls.has(url.url_id) ? '⏳' : '🚫',
                                variant: 'warning',
                                disabled: reindexingUrls.has(url.url_id)
                              },
                              {
                                label: 'Reject URL',
                                onClick: () => handleRejectUrl(url),
                                icon: reindexingUrls.has(url.url_id) ? '⏳' : '❌',
                                variant: 'danger',
                                disabled: reindexingUrls.has(url.url_id)
                              },
                              {
                                label: 'Delete URL',
                                onClick: () => handleDeleteUrl(url),
                                icon: '🗑️',
                                variant: 'danger'
                              }
                            ]}
                            size="sm"
                          />
                        </td>
                      </tr>
                    );
                  })}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* Add URL Modal */}
          <Modal
            isOpen={showAddUrlModal}
            onClose={() => {
              setShowAddUrlModal(false);
              setNewUrl('');
            }}
            title="Add New URL"
          >
            <div className="p-6">
              <div className="mb-4">
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  URL Path
                </label>
                <div className="flex">
                  <span className="inline-flex items-center px-3 rounded-l-md border border-r-0 border-gray-300 bg-gray-50 text-gray-500 text-sm">
                    {domain.base_url}
                  </span>
                  <input
                    type="text"
                    value={newUrl}
                    onChange={(e) => setNewUrl(e.target.value)}
                    className="flex-1 min-w-0 block w-full px-3 py-2 rounded-none rounded-r-md border border-gray-300 focus:ring-blue-500 focus:border-blue-500"
                    placeholder="/page-path"
                    onKeyPress={(e) => e.key === 'Enter' && handleAddUrl()}
                  />
                </div>
                <p className="mt-2 text-sm text-gray-500">
                  Enter the URL path (e.g., "/about" or "/products/item-1")
                </p>
              </div>
              <div className="flex justify-end gap-3">
                <button
                  onClick={() => {
                    setShowAddUrlModal(false);
                    setNewUrl('');
                  }}
                  className="px-4 py-2 text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={handleAddUrl}
                  disabled={!newUrl.trim() || addingUrl}
                  className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors disabled:opacity-50"
                >
                  {addingUrl ? (
                    <div className="flex items-center gap-2">
                      <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                      Adding...
                    </div>
                  ) : (
                    'Add URL'
                  )}
                </button>
              </div>
            </div>
          </Modal>

          {/* Delete URL Modal */}
          <Modal
            isOpen={showDeleteModal}
            onClose={() => {
              setShowDeleteModal(false);
              setUrlToDelete(null);
            }}
            title="Delete URL"
          >
            <div className="p-6">
              <p className="text-gray-700 mb-6">
                Are you sure you want to delete this URL? This will also remove its indexed content from the silo.
              </p>
              <div className="bg-gray-50 rounded-lg p-3 mb-6">
                <p className="text-sm text-gray-600 font-mono">
                  {domain.base_url}{urlToDelete?.url}
                </p>
              </div>
              <div className="flex justify-end gap-3">
                <button
                  onClick={() => {
                    setShowDeleteModal(false);
                    setUrlToDelete(null);
                  }}
                  className="px-4 py-2 text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={confirmDeleteUrl}
                  disabled={deletingUrl}
                  className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg transition-colors disabled:opacity-50"
                >
                  {deletingUrl ? (
                    <div className="flex items-center gap-2">
                      <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                      Deleting...
                    </div>
                  ) : (
                    'Delete'
                  )}
                </button>
              </div>
            </div>
          </Modal>

          {/* Unindex URL Modal */}
          <Modal
            isOpen={showUnindexModal}
            onClose={() => {
              setShowUnindexModal(false);
              setUrlToUnindex(null);
            }}
            title="Unindex URL"
          >
            <div className="p-6">
              <p className="text-gray-700 mb-6">
                Are you sure you want to unindex this URL? This will remove its content from the search index, but it can be re-indexed later.
              </p>
              <div className="bg-gray-50 rounded-lg p-3 mb-6">
                <p className="text-sm text-gray-600 font-mono">
                  {domain.base_url}{urlToUnindex?.url}
                </p>
              </div>
              <div className="flex justify-end gap-3">
                <button
                  onClick={() => {
                    setShowUnindexModal(false);
                    setUrlToUnindex(null);
                  }}
                  className="px-4 py-2 text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={confirmUnindexUrl}
                  disabled={unindexingUrl}
                  className="px-4 py-2 bg-yellow-600 hover:bg-yellow-700 text-white rounded-lg transition-colors disabled:opacity-50"
                >
                  {unindexingUrl ? (
                    <div className="flex items-center gap-2">
                      <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                      Unindexing...
                    </div>
                  ) : (
                    'Unindex'
                  )}
                </button>
              </div>
            </div>
          </Modal>

          {/* Reject URL Modal */}
          <Modal
            isOpen={showRejectModal}
            onClose={() => {
              setShowRejectModal(false);
              setUrlToReject(null);
            }}
            title="Reject URL"
          >
            <div className="p-6">
              <p className="text-gray-700 mb-6">
                Are you sure you want to reject this URL? This will permanently exclude it from auto-indexing. Rejected URLs will never be indexed automatically.
              </p>
              <div className="bg-gray-50 rounded-lg p-3 mb-6">
                <p className="text-sm text-gray-600 font-mono">
                  {domain.base_url}{urlToReject?.url}
                </p>
              </div>
              <div className="flex justify-end gap-3">
                <button
                  onClick={() => {
                    setShowRejectModal(false);
                    setUrlToReject(null);
                  }}
                  className="px-4 py-2 text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={confirmRejectUrl}
                  disabled={rejectingUrl}
                  className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg transition-colors disabled:opacity-50"
                >
                  {rejectingUrl ? (
                    <div className="flex items-center gap-2">
                      <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                      Rejecting...
                    </div>
                  ) : (
                    'Reject'
                  )}
                </button>
              </div>
            </div>
          </Modal>

          {/* Content Preview Modal */}
          <Modal
            isOpen={showContentModal}
            onClose={() => {
              setShowContentModal(false);
              setUrlContent(null);
            }}
            title="URL Content Preview"
            size="xlarge"
          >
            <div className="p-6">
              {loadingContent ? (
                <div className="flex justify-center items-center py-8">
                  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
                  <span className="ml-3 text-gray-600">Loading content...</span>
                </div>
              ) : urlContent ? (
                <div>
                  <div className="mb-4">
                    <h3 className="text-lg font-medium text-gray-900 mb-2">URL:</h3>
                    <p className="text-sm text-gray-600 font-mono bg-gray-50 p-2 rounded">
                      {urlContent.url}
                    </p>
                  </div>
                  
                  <div className="mb-4">
                    <h3 className="text-lg font-medium text-gray-900 mb-2">Scraped Content:</h3>
                    {urlContent.content ? (
                      <div className="bg-gray-50 border rounded-lg p-4 max-h-96 overflow-y-auto">
                        <pre className="whitespace-pre-wrap text-sm text-gray-700">
                          {urlContent.content}
                        </pre>
                      </div>
                    ) : (
                      <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
                        <p className="text-yellow-700">{urlContent.message}</p>
                      </div>
                    )}
                  </div>
                </div>
              ) : (
                <div className="text-center py-8">
                  <p className="text-gray-500">No content available</p>
                </div>
              )}
              
              <div className="flex justify-end mt-6">
                <button
                  onClick={() => {
                    setShowContentModal(false);
                    setUrlContent(null);
                  }}
                  className="px-4 py-2 bg-gray-100 hover:bg-gray-200 text-gray-700 rounded-lg transition-colors"
                >
                  Close
                </button>
              </div>
            </div>
          </Modal>
        </div>
      )}
    </div>
  );
};

export default DomainDetailPage; 