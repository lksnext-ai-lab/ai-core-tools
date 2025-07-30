import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { apiService } from '../services/api';
import Modal from '../components/ui/Modal';

interface URL {
  url_id: number;
  url: string;
  created_at: string;
  last_indexed?: string;
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
  
  // Content preview modal
  const [showContentModal, setShowContentModal] = useState(false);
  const [urlContent, setUrlContent] = useState<{url: string, content: string | null, message: string} | null>(null);
  const [loadingContent, setLoadingContent] = useState(false);
  
  // Reindex states
  const [reindexingUrls, setReindexingUrls] = useState<Set<number>>(new Set());
  const [reindexingDomain, setReindexingDomain] = useState(false);

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
      await apiService.deleteUrlFromDomain(parseInt(appId), parseInt(domainId), urlToDelete.url_id);
      setUrls(urls.filter(u => u.url_id !== urlToDelete.url_id));
      setShowDeleteModal(false);
      setUrlToDelete(null);
    } catch (err) {
      console.error('Error deleting URL:', err);
      alert('Failed to delete URL');
    }
  };

  const handleReindexUrl = async (urlId: number) => {
    if (!appId || !domainId) return;
    
    try {
      setReindexingUrls(prev => new Set(prev).add(urlId));
      await apiService.reindexUrl(parseInt(appId), parseInt(domainId), urlId);
      await loadUrls(); // Reload to get updated timestamps
    } catch (err) {
      console.error('Error reindexing URL:', err);
      alert('Failed to reindex URL');
    } finally {
      setReindexingUrls(prev => {
        const newSet = new Set(prev);
        newSet.delete(urlId);
        return newSet;
      });
    }
  };

  const handleReindexDomain = async () => {
    if (!appId || !domainId) return;
    
    try {
      setReindexingDomain(true);
      await apiService.reindexDomain(parseInt(appId), parseInt(domainId));
      await loadUrls(); // Reload to get updated timestamps
    } catch (err) {
      console.error('Error reindexing domain:', err);
      alert('Failed to reindex domain');
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
    
    if (url.last_indexed) {
      return {
        text: 'Indexed',
        badge: 'bg-green-100 text-green-800',
        icon: '✅'
      };
    }
    
    return {
      text: 'Not Indexed',
      badge: 'bg-gray-100 text-gray-800',
      icon: '⚪'
    };
  };

  if (loading) {
    return (
      <div className="container mx-auto px-4 py-8">
        <div className="flex justify-center items-center h-64">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
        </div>
      </div>
    );
  }

  if (error || !domain) {
    return (
      <div className="container mx-auto px-4 py-8">
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg mb-6">
          {error || 'Domain not found'}
        </div>
        <div>
          <button
            onClick={() => navigate(`/apps/${appId}/domains`)}
            className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg"
          >
            Back to Domains
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="container mx-auto px-4 py-8">
      {/* Header */}
      <div className="flex justify-between items-start mb-8">
        <div>
          <div className="flex items-center gap-3 mb-2">
            <button
              onClick={() => navigate(`/apps/${appId}/domains`)}
              className="text-gray-500 hover:text-gray-700 transition-colors"
            >
              ← Back
            </button>
            <h1 className="text-3xl font-bold text-gray-900">{domain.name}</h1>
          </div>
          <p className="text-gray-600 mb-2">
            Created {formatDate(domain.created_at)} • {urls.length} URLs
          </p>
          <p className="text-gray-600">
            <span className="font-medium">Base URL:</span> {domain.base_url}
          </p>
          {domain.description && (
            <p className="text-gray-600 mt-1">
              <span className="font-medium">Description:</span> {domain.description}
            </p>
          )}
        </div>
        
        <div className="flex gap-3">
          <button
            onClick={() => setShowAddUrlModal(true)}
            className="bg-green-600 hover:bg-green-700 text-white px-4 py-2 rounded-lg flex items-center gap-2"
          >
            <span>➕</span>
            Add URL
          </button>
          <button
            onClick={handleReindexDomain}
            disabled={reindexingDomain || urls.length === 0}
            className="bg-orange-600 hover:bg-orange-700 text-white px-4 py-2 rounded-lg flex items-center gap-2 disabled:opacity-50"
          >
            {reindexingDomain ? (
              <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
            ) : (
              <span>🔄</span>
            )}
            Reindex All
          </button>
          <button
            onClick={() => navigate(`/apps/${appId}/domains/${domainId}/edit`)}
            className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg flex items-center gap-2"
          >
            <span>✏️</span>
            Edit
          </button>
        </div>
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
        <div className="px-6 py-4 border-b border-gray-200">
          <h2 className="text-xl font-semibold text-gray-900">URLs ({urls.length})</h2>
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
          <div className="overflow-x-auto">
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
                        {url.last_indexed ? formatDate(url.last_indexed) : 'Never'}
                      </td>
                    <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                      <div className="flex justify-end gap-2">
                        <button
                          onClick={() => handleViewContent(url)}
                          className="text-green-600 hover:text-green-900 px-3 py-1 rounded-md hover:bg-green-50"
                          title="View Content"
                        >
                          👁️
                        </button>
                        <button
                          onClick={() => handleReindexUrl(url.url_id)}
                          disabled={reindexingUrls.has(url.url_id)}
                          className="text-blue-600 hover:text-blue-900 px-3 py-1 rounded-md hover:bg-blue-50 disabled:opacity-50"
                          title="Reindex URL"
                        >
                          {reindexingUrls.has(url.url_id) ? (
                            <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-blue-600"></div>
                          ) : (
                            '🔄'
                          )}
                        </button>
                        <button
                          onClick={() => handleDeleteUrl(url)}
                          className="text-red-600 hover:text-red-900 px-3 py-1 rounded-md hover:bg-red-50"
                          title="Delete URL"
                        >
                          🗑️
                        </button>
                      </div>
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
              className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg transition-colors"
            >
              Delete
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
  );
};

export default DomainDetailPage; 