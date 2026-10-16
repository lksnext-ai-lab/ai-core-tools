import React, { useState, useEffect, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import { apiService } from '../services/api';
import SearchFilters from '../components/playground/SearchFilters';
import type { SearchFilterMetadataField } from '../components/playground/SearchFilters';
import Title from '../components/ui/Title';
import { FormField } from '../components/ui/FormField';
import ButtonApp from '../components/ui/ButtonApp';
import { Search } from 'lucide-react';
import Alert from '../components/ui/Alert';
import CardApp from '../components/ui/CardApp';

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
  metadata: Record<string, unknown>;
  score?: number;
}

const RepositoryPlaygroundPage: React.FC = () => {
  const { appId, repositoryId } = useParams<{ appId: string; repositoryId: string }>();
  {/*const navigate = useNavigate();*/}
  
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [repository, setRepository] = useState<Repository | null>(null);
  const [hasSearched, setHasSearched] = useState(false);
  const [filterMetadata, setFilterMetadata] = useState<Record<string, unknown> | undefined>(undefined);

  useEffect(() => {
    if (appId && repositoryId) {
      void loadRepositoryInfo();
    }
  }, [appId, repositoryId]);

  const loadRepositoryInfo = async () => {
    try {
      const repositoryData = await apiService.getRepository(Number.parseInt(appId!), Number.parseInt(repositoryId!));
      setRepository(repositoryData);
      
      // The metadata_fields should already be included in the repository response from the backend
      // If not available and there's a silo_id, we can try to load it separately
      if (!repositoryData.metadata_fields?.length && repositoryData.silo_id) {
        try {
          const siloData = await apiService.getSilo(Number.parseInt(appId!), repositoryData.silo_id);
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
        Number.parseInt(appId!), 
        Number.parseInt(repositoryId!), 
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

  {/*const handleGoBack = () => {
    // Go back to the previous page in history
    navigate(-1);
  };*/}

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
          <Title variant="titSecundario" titulo="Repository Search" subtitulo={`Search within "${repository?.name || 'Repository'}" repository`} subtitleMarginBottom={20} />
        </div>
      </div>

      {/* Search Form */}
      <CardApp variant="white" className=" p-6 mb-8">
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
          
          <div className="flex items-end gap-3">
              <FormField
                label="Search Query"
                id="query"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Enter your search query (leave empty to browse all documents)..."
                disabled={searching}
                className="flex-1"
              />
              <ButtonApp
                type="submit"
                disabled={searching}
                loading={searching}
                icon={<Search className="w-4 h-4" aria-hidden="true" />}
                label="Search"
                variant="secondary"
                size="medium"
              />
          </div>
        </form>
      </CardApp>

      {/* Error Message */}
      {error && <Alert type="error" message={error} className="mb-6" />}

      {/* Search Results */}
      {results.length > 0 && (
        <CardApp variant="white" className="p-6">
          <h2 className="text-lg font-semibold text-fg dark:text-fg-dark mb-4">
            Search Results ({results.length})
          </h2>
          
          <div className="space-y-4">
            {results.map((result, index) => {
              const source = result.metadata.source as string | undefined;
              const page = result.metadata.page as number | undefined;
              const uniqueKey = `${source}-${page ?? 'no-page'}-${result.page_content.substring(0, 30).replaceAll(/\s+/g, '-').replaceAll(/[^a-zA-Z0-9-]/g, '')}`;
              return (
              <CardApp variant="white" key={uniqueKey} className="p-4">
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
              </CardApp>
            );
            })}
          </div>
        </CardApp>
      )}

      {/* No Results State */}
      {!searching && results.length === 0 && hasSearched && (
        <CardApp variant="white" className="p-6">
          <div className="text-center">
            <Search className="w-10 h-10 text-fg-secondary dark:text-fg-secondary-dark mx-auto mb-4" />
            <h3 className="text-lg font-medium text-fg dark:text-fg-dark mb-2">No Results Found</h3>
            <p className="text-fg-secondary dark:text-fg-secondary-dark">
              {query ? 
                "Try adjusting your search query or check if the repository contains documents." :
                "Enter a search query to find documents, or leave empty to see all available documents."
              }
            </p>
          </div>
        </CardApp>
      )}

      {/* Help Section */}
      <Alert
        type="info"
        title="How to Use the Repository Playground"
        className="mt-2"
        message={(
          <>
            <p>
              The playground allows you to test semantic search within your repository. 
              Enter natural language queries to find relevant documents.
            </p>
            <p className="mt-2">
              <span className="font-medium">Tips:</span>
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
          </>
        )}
      />
    </div>
  );
};

export default RepositoryPlaygroundPage; 