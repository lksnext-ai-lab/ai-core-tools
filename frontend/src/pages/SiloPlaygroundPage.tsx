import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { AlertTriangle, ArrowLeft, Search, Info } from 'lucide-react';
import { apiService } from '../services/api';
import SearchControls, { type SearchControlsValue, DEFAULT_SEARCH_CONTROLS } from '../components/playground/SearchControls';
import SearchFilters from '../components/playground/SearchFilters';
import type {
  SearchFilterMetadataField,
  SupportedDbType,
} from '../components/playground/SearchFilters';
import ResultCard, { type SearchResult } from '../components/playground/ResultCard';

// Define the Silo type
interface Silo {
  silo_id: number;
  name: string;
  type?: string;
  created_at?: string;
  docs_count: number;
  metadata_fields?: SearchFilterMetadataField[];
}

const DEFAULT_DB_TYPE: SupportedDbType = 'PGVECTOR';

function SiloPlaygroundPage() {
  const [systemDBConfig, setSystemDBConfig] = useState('');
  const { appId, siloId } = useParams();
  const navigate = useNavigate();
  const [silo, setSilo] = useState<Silo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [hasSearched, setHasSearched] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [filterMetadata, setFilterMetadata] = useState<Record<string, any> | undefined>(undefined);
  const [searchControls, setSearchControls] = useState<SearchControlsValue>(DEFAULT_SEARCH_CONTROLS);

  // Load silo data
  useEffect(() => {
    if (appId && siloId) {
      void loadSilo();
    }
  }, [appId, siloId]);


  async function loadSilo() {
    if (!appId || !siloId) return;
    
    try {
      setLoading(true);
      setError(null);
      const response = await apiService.getSilo(Number.parseInt(appId), Number.parseInt(siloId));
      setSilo(response);
      setSystemDBConfig(response.vector_db_type ? response.vector_db_type.toUpperCase() : DEFAULT_DB_TYPE);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load silo');
      console.error('Error loading silo:', err);
    } finally {
      setLoading(false);
    }
  }

  async function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    
    if (!appId || !siloId) return;

    try {
      setIsSearching(true);
      setSearchError(null);
      setSearchResults([]);
      setHasSearched(true);
      const response = await apiService.searchSiloDocuments(
        Number.parseInt(appId),
        Number.parseInt(siloId),
        searchQuery,
        searchControls.limit,
        filterMetadata,
        {
          searchType: searchControls.searchType,
          scoreThreshold: searchControls.searchType === 'similarity_score_threshold' ? searchControls.scoreThreshold : undefined,
          fetchK: searchControls.searchType === 'mmr' ? searchControls.fetchK : undefined,
          lambdaMult: searchControls.searchType === 'mmr' ? searchControls.lambdaMult : undefined,
        },
      );
      
      // Extract _id from metadata and set as top-level id field
      const resultsWithIds = (response.results || []).map((result: SearchResult) => ({
        ...result,
        id: result.metadata?._id as string | undefined,  // Extract document ID from metadata
      }));
      setSearchResults(resultsWithIds);
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

  const handleFilterMetadataChange = useCallback((metadata: Record<string, any> | undefined) => {
    setFilterMetadata(metadata);
  }, []);

  async function handleDeleteDocument(result: SearchResult, index: number) {
    if (!appId || !siloId || !result.id) {
      alert('Cannot delete: Document ID not available');
      return;
    }
    
    if (!globalThis.confirm('Are you sure you want to delete this document from the silo? This action cannot be undone.')) {
      return;
    }

    try {
      setDeletingId(result.id);
      
      // Delete using document ID
      await apiService.deleteSiloDocuments(
        Number.parseInt(appId),
        Number.parseInt(siloId),
        [result.id]  // Pass as array of IDs
      );
      
      // Remove from results locally
      setSearchResults(prev => prev.filter((_, i) => i !== index));
      
      // Reload silo to update document count
      await loadSilo();
      
    } catch (err) {
      console.error('Error deleting document:', err);
      setSearchError(err instanceof Error ? err.message : 'Failed to delete document');
    } finally {
      setDeletingId(null);
    }
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
            <AlertTriangle className="w-5 h-5 text-red-400 mr-3 shrink-0" />
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
            <AlertTriangle className="w-5 h-5 text-yellow-400 mr-3 shrink-0" />
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

  const maxScore =
    searchResults.length > 0
      ? Math.max(...searchResults.map((r) => r.score ?? 0))
      : 0;

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
          <ArrowLeft className="w-4 h-4 inline-block mr-1" /> Back to Silos
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
          <SearchFilters
            metadataFields={silo.metadata_fields}
            dbType={systemDBConfig}
            disabled={isSearching}
            onFilterMetadataChange={handleFilterMetadataChange}
            appId={appId}
            siloId={siloId}
            siloStorageKey={siloId}
          />

          <SearchControls
            siloId={siloId ?? ''}
            value={searchControls}
            onChange={setSearchControls}
            disabled={isSearching}
          />

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
                placeholder="Enter your search query (leave empty to browse all documents)..."
                className="flex-1 px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-yellow-500 focus:border-transparent"
                disabled={isSearching}
              />
              <button
                type="submit"
                disabled={isSearching}
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
              <AlertTriangle className="w-5 h-5 text-red-400 mr-3 shrink-0" />
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
              <ResultCard
                key={result.id ?? `result-${index}`}
                result={result}
                index={index}
                maxScore={maxScore}
                onDelete={handleDeleteDocument}
                isDeleting={deletingId === result.id}
                appId={appId ?? ''}
                siloId={siloId ?? ''}
              />
            ))}
          </div>
        </div>
      )}

      {/* Empty State */}
      {!isSearching && searchResults.length === 0 && hasSearched && !searchError && (
        <div className="bg-white shadow rounded-lg p-6">
          <div className="text-center">
            <Search className="w-10 h-10 text-gray-400 mx-auto mb-4" />
            <h3 className="text-lg font-medium text-gray-900 mb-2">No Results Found</h3>
            <div className="text-sm text-gray-500 space-y-1 max-w-md mx-auto text-left">
              {searchControls.searchType === 'similarity_score_threshold' && (
                <p>⬇️ Try lowering the score threshold (currently {searchControls.scoreThreshold}).</p>
              )}
              {filterMetadata && Object.keys(filterMetadata).length > 0 && (
                <p>🔍 Try removing or relaxing metadata filters.</p>
              )}
              {searchControls.limit < 20 && (
                <p>⬆️ Try increasing Top K (currently {searchControls.limit}).</p>
              )}
              <p className="text-gray-400 mt-2">
                {searchQuery
                  ? 'No documents matched your query with the current settings.'
                  : 'The silo may be empty or filters are too restrictive.'}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Help Section */}
      <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
        <div className="flex">
          <div className="flex-shrink-0">
            <Info className="w-5 h-5 text-blue-400" />
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
                • Leave empty to browse all available documents
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