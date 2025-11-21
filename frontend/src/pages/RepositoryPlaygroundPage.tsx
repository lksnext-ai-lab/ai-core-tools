import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { apiService } from '../services/api';
import SearchFilters from '../components/playground/SearchFilters';
import type { SearchFilterMetadataField } from '../components/playground/SearchFilters';

// Define the repository type
interface Repository {
  repository_id: number;
  name: string;
  created_at?: string;
  resources: any[];
  embedding_services: any[];
  embedding_service_id?: number;
  metadata_fields?: SearchFilterMetadataField[];
  vector_db_type?: string;
  silo_id?: number;
}

interface SearchResult {
  page_content: string;
  metadata: {
    source: string;
    page?: number;
    [key: string]: any;
  };
  score?: number;
}

const RepositoryPlaygroundPage: React.FC = () => {
  const { appId, repositoryId } = useParams<{ appId: string; repositoryId: string }>();
  const navigate = useNavigate();
  
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [repository, setRepository] = useState<Repository | null>(null);
  const [hasSearched, setHasSearched] = useState(false);
  const [filterMetadata, setFilterMetadata] = useState<Record<string, unknown> | undefined>(undefined);

  useEffect(() => {
    if (appId && repositoryId) {
      loadRepositoryInfo();
    }
  }, [appId, repositoryId]);

  const loadRepositoryInfo = async () => {
    try {
      const repositoryData = await apiService.getRepository(parseInt(appId!), parseInt(repositoryId!));
      setRepository(repositoryData);
      
      // The metadata_fields should already be included in the repository response from the backend
      // If not available and there's a silo_id, we can try to load it separately
      if (!repositoryData.metadata_fields?.length && repositoryData.silo_id) {
        try {
          const siloData = await apiService.getSilo(parseInt(appId!), repositoryData.silo_id);
          setRepository(prev => ({
            ...prev!,
            metadata_fields: siloData.metadata_fields || []
          }));
        } catch (siloErr) {
          console.warn('Could not load silo metadata fields:', siloErr);
        }
      }
    } catch (err) {
      console.error('Error loading repository info:', err);
      setError('Failed to load repository information');
    }
  };

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();

    try {
      setSearching(true);
      setError(null);
      setResults([]);
      setHasSearched(true);

      const hasFilters = filterMetadata !== undefined && Object.keys(filterMetadata).length > 0;
      const searchFilters = hasFilters ? filterMetadata as Record<string, any> : undefined;

      // Use the repository search API with filters
      const response = await apiService.searchRepositoryDocuments(
        parseInt(appId!), 
        parseInt(repositoryId!), 
        query,
        10,
        searchFilters
      );
      
      setResults(response.results || []);

    } catch (err) {
      console.error('Error searching repository:', err);
      setError('Failed to search repository');
    } finally {
      setSearching(false);
    }
  };

  const handleGoBack = () => {
    // Go back to the previous page in history
    navigate(-1);
  };

  const handleFilterMetadataChange = useCallback((metadata: Record<string, unknown> | undefined) => {
    setFilterMetadata(metadata);
  }, []);

  useEffect(() => {
    const fields = repository?.metadata_fields;
    if ((!fields || fields.length === 0) && filterMetadata !== undefined) {
      setFilterMetadata(undefined);
    }
  }, [repository, filterMetadata]);

  return (
    <div className="container mx-auto px-4 py-8">
      {/* Header */}
      <div className="flex justify-between items-start mb-8">
        <div>
          <div className="flex items-center gap-3 mb-2">
            <button
              onClick={handleGoBack}
              className="text-gray-500 hover:text-gray-700 transition-colors"
            >
              ← Back
            </button>
            <h1 className="text-3xl font-bold text-gray-900">Repository Search</h1>
          </div>
          <p className="text-gray-600">
            Search within "{repository?.name || 'Repository'}" repository
          </p>
        </div>
      </div>

      {/* Search Form */}
      <div className="bg-white border border-gray-200 rounded-lg p-6 mb-8">
        <form onSubmit={handleSearch} className="space-y-4">
          {/* Metadata Filters */}
          {repository?.metadata_fields && repository.metadata_fields.length > 0 && (
            <SearchFilters
              metadataFields={repository.metadata_fields}
              dbType={repository.vector_db_type?.toUpperCase()}
              disabled={searching}
              onFilterMetadataChange={handleFilterMetadataChange}
            />
          )}
          
          <div>
            <label htmlFor="query" className="block text-sm font-medium text-gray-700 mb-2">
              Search Query
            </label>
            <div className="flex gap-3">
              <input
                type="text"
                id="query"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Enter your search query (leave empty to browse all documents)..."
                className="flex-1 px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                disabled={searching}
              />
              <button
                type="submit"
                disabled={searching}
                className="px-6 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
              >
                {searching ? (
                  <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                ) : (
                  <span>🔍</span>
                )}
                Search
              </button>
            </div>
          </div>
        </form>
      </div>

      {/* Error Message */}
      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg mb-6">
          {error}
        </div>
      )}

      {/* Search Results */}
      {results.length > 0 && (
        <div className="bg-white shadow rounded-lg p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">
            Search Results ({results.length})
          </h2>
          
          <div className="space-y-4">
            {results.map((result, index) => {
              const uniqueKey = `${result.metadata.source}-${result.metadata.page ?? 'no-page'}-${result.page_content.substring(0, 30).replace(/\s+/g, '-').replace(/[^a-zA-Z0-9-]/g, '')}`;
              return (
              <div key={uniqueKey} className="border border-gray-200 rounded-lg p-4">
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
            );
            })}
          </div>
        </div>
      )}

      {/* No Results State */}
      {!searching && results.length === 0 && hasSearched && (
        <div className="bg-white shadow rounded-lg p-6">
          <div className="text-center">
            <span className="text-gray-400 text-4xl mb-4">🔍</span>
            <h3 className="text-lg font-medium text-gray-900 mb-2">No Results Found</h3>
            <p className="text-gray-600">
              {query ? 
                "Try adjusting your search query or check if the repository contains documents." :
                "Enter a search query to find documents, or leave empty to see all available documents."
              }
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
              How to Use the Repository Playground
            </h3>
            <div className="mt-2 text-sm text-blue-700">
              <p>
                The playground allows you to test semantic search within your repository. 
                Enter natural language queries to find relevant documents.
              </p>
              <p className="mt-2">
                <strong>Tips:</strong>
                <br />
                • Use natural language (e.g., "What is machine learning?")
                <br />
                • Leave empty to browse all available documents
                <br />
                • Try different phrasings for better results
                <br />
                • Results are ranked by relevance score
                <br />
                • Use metadata filters to narrow down your search
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default RepositoryPlaygroundPage; 