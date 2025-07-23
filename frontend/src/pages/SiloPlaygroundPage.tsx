import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { apiService } from '../services/api';

// Define the Silo type
interface Silo {
  silo_id: number;
  name: string;
  type?: string;
  created_at?: string;
  docs_count: number;
  metadata_fields?: MetadataField[];
}

// Define the metadata field type
interface MetadataField {
  name: string;
  type: string;
  description: string;
}

// Define the search result type
interface SearchResult {
  page_content: string;
  metadata: Record<string, any>;
  score?: number;
}

function SiloPlaygroundPage() {
  const { appId, siloId } = useParams();
  const navigate = useNavigate();
  const [silo, setSilo] = useState<Silo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [metadataFilters, setMetadataFilters] = useState<Record<string, string>>({});

  // Load silo data
  useEffect(() => {
    if (appId && siloId) {
      loadSilo();
    }
  }, [appId, siloId]);

  async function loadSilo() {
    if (!appId || !siloId) return;
    
    try {
      setLoading(true);
      setError(null);
      const response = await apiService.getSilo(parseInt(appId), parseInt(siloId));
      setSilo(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load silo');
      console.error('Error loading silo:', err);
    } finally {
      setLoading(false);
    }
  }

  async function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    
    if (!searchQuery.trim() || !appId || !siloId) return;

    try {
      setIsSearching(true);
      setSearchError(null);
      setSearchResults([]);
      
      // Build metadata filter object
      const filterMetadata: Record<string, any> = {};
      Object.entries(metadataFilters).forEach(([fieldName, value]) => {
        if (value.trim()) {
          filterMetadata[fieldName] = { $eq: value.trim() };
        }
      });
      
      const response = await apiService.searchSiloDocuments(
        parseInt(appId), 
        parseInt(siloId), 
        searchQuery,
        10,
        Object.keys(filterMetadata).length > 0 ? filterMetadata : undefined
      );
      
      setSearchResults(response.results || []);
    } catch (err) {
      setSearchError(err instanceof Error ? err.message : 'Search failed');
      console.error('Error searching silo:', err);
    } finally {
      setIsSearching(false);
    }
  }

  function handleBack() {
    navigate(`/apps/${appId}/silos`);
  }

  function handleMetadataFilterChange(fieldName: string, value: string) {
    setMetadataFilters(prev => ({
      ...prev,
      [fieldName]: value
    }));
  }

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-center py-12">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-yellow-600"></div>
          <span className="ml-2">Loading silo...</span>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-6">
        <div className="bg-red-50 border border-red-200 rounded-lg p-4">
          <div className="flex">
            <span className="text-red-400 text-xl mr-3">⚠️</span>
            <div>
              <h3 className="text-sm font-medium text-red-800">Error Loading Silo</h3>
              <p className="text-sm text-red-600 mt-1">{error}</p>
              <button 
                onClick={handleBack}
                className="mt-2 text-sm text-red-800 hover:text-red-900 underline"
              >
                Back to Silos
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (!silo) {
    return (
      <div className="space-y-6">
        <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
          <div className="flex">
            <span className="text-yellow-400 text-xl mr-3">⚠️</span>
            <div>
              <h3 className="text-sm font-medium text-yellow-800">Silo Not Found</h3>
              <p className="text-sm text-yellow-600 mt-1">The requested silo could not be found.</p>
              <button 
                onClick={handleBack}
                className="mt-2 text-sm text-yellow-800 hover:text-yellow-900 underline"
              >
                Back to Silos
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">
            Silo Playground: {silo.name}
          </h1>
          <p className="text-gray-600">
            Test semantic search and explore documents in this silo
          </p>
        </div>
        <button
          onClick={handleBack}
          className="px-4 py-2 text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-lg"
        >
          ← Back to Silos
        </button>
      </div>

      {/* Silo Info */}
      <div className="bg-white shadow rounded-lg p-6">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <h3 className="text-sm font-medium text-gray-500">Silo Type</h3>
            <p className="text-lg font-semibold text-gray-900">
              {silo.type || 'Custom'}
            </p>
          </div>
          <div>
            <h3 className="text-sm font-medium text-gray-500">Documents</h3>
            <p className="text-lg font-semibold text-gray-900">
              {silo.docs_count.toLocaleString()}
            </p>
          </div>
          <div>
            <h3 className="text-sm font-medium text-gray-500">Created</h3>
            <p className="text-lg font-semibold text-gray-900">
              {silo.created_at ? new Date(silo.created_at).toLocaleDateString() : 'Unknown'}
            </p>
          </div>
        </div>
      </div>

      {/* Search Interface */}
      <div className="bg-white shadow rounded-lg p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Search Documents</h2>
        
        <form onSubmit={handleSearch} className="space-y-4">
          {/* Metadata Filters */}
          {silo.metadata_fields && silo.metadata_fields.length > 0 && (
            <div className="border border-gray-200 rounded-lg p-4 bg-gray-50">
              <h3 className="text-sm font-medium text-gray-700 mb-3">
                <span className="mr-2">🔍</span>
                Filter by Metadata
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {silo.metadata_fields.map((field) => (
                  <div key={field.name}>
                    <label htmlFor={`filter_${field.name}`} className="block text-sm font-medium text-gray-700 mb-1">
                      {field.name}
                      <span className="text-xs text-gray-500 ml-1">({field.type})</span>
                    </label>
                    <input
                      type="text"
                      id={`filter_${field.name}`}
                      value={metadataFilters[field.name] || ''}
                      onChange={(e) => handleMetadataFilterChange(field.name, e.target.value)}
                      placeholder={`Filter by ${field.name}`}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-yellow-500 focus:border-transparent text-sm"
                      disabled={isSearching}
                    />
                    {field.description && (
                      <p className="text-xs text-gray-500 mt-1">{field.description}</p>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Search Query */}
          <div>
            <label htmlFor="searchQuery" className="block text-sm font-medium text-gray-700 mb-2">
              Search Query
            </label>
            <div className="flex gap-2">
              <input
                type="text"
                id="searchQuery"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Enter your search query..."
                className="flex-1 px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-yellow-500 focus:border-transparent"
                disabled={isSearching}
              />
              <button
                type="submit"
                disabled={isSearching || !searchQuery.trim()}
                className="px-6 py-2 bg-yellow-600 hover:bg-yellow-700 disabled:bg-yellow-400 text-white rounded-lg flex items-center"
              >
                {isSearching && (
                  <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
                )}
                {isSearching ? 'Searching...' : 'Search'}
              </button>
            </div>
          </div>
        </form>

        {/* Search Error */}
        {searchError && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-4">
            <div className="flex">
              <span className="text-red-400 text-xl mr-3">⚠️</span>
              <div>
                <h3 className="text-sm font-medium text-red-800">Search Error</h3>
                <p className="text-sm text-red-600 mt-1">{searchError}</p>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Search Results */}
      {searchResults.length > 0 && (
        <div className="bg-white shadow rounded-lg p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">
            Search Results ({searchResults.length})
          </h2>
          
          <div className="space-y-4">
            {searchResults.map((result, index) => (
              <div key={index} className="border border-gray-200 rounded-lg p-4">
                <div className="flex items-start justify-between mb-2">
                  <span className="text-sm font-medium text-gray-500">
                    Result #{index + 1}
                  </span>
                  {result.score && (
                    <span className="text-sm text-gray-500">
                      Score: {result.score.toFixed(3)}
                    </span>
                  )}
                </div>
                
                <div className="mb-3">
                  <h3 className="text-sm font-medium text-gray-700 mb-1">Content:</h3>
                  <p className="text-gray-900 text-sm leading-relaxed">
                    {result.page_content}
                  </p>
                </div>
                
                {result.metadata && Object.keys(result.metadata).length > 0 && (
                  <div>
                    <h3 className="text-sm font-medium text-gray-700 mb-1">Metadata:</h3>
                    <div className="bg-gray-50 rounded p-2">
                      <pre className="text-xs text-gray-600 overflow-x-auto">
                        {JSON.stringify(result.metadata, null, 2)}
                      </pre>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Empty State */}
      {!isSearching && searchResults.length === 0 && searchQuery && !searchError && (
        <div className="bg-white shadow rounded-lg p-6">
          <div className="text-center">
            <span className="text-gray-400 text-4xl mb-4">🔍</span>
            <h3 className="text-lg font-medium text-gray-900 mb-2">No Results Found</h3>
            <p className="text-gray-600">
              Try adjusting your search query or check if the silo contains documents.
            </p>
          </div>
        </div>
      )}

      {/* Help Section */}
      <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
        <div className="flex">
          <div className="flex-shrink-0">
            <span className="text-blue-400 text-xl">ℹ️</span>
          </div>
          <div className="ml-3">
            <h3 className="text-sm font-medium text-blue-800">
              How to Use the Playground
            </h3>
            <div className="mt-2 text-sm text-blue-700">
              <p>
                The playground allows you to test semantic search within your silo. 
                Enter natural language queries to find relevant documents.
              </p>
              <p className="mt-2">
                <strong>Tips:</strong>
                <br />
                • Use natural language (e.g., "What is machine learning?")
                <br />
                • Try different phrasings for better results
                <br />
                • Results are ranked by relevance score
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default SiloPlaygroundPage; 