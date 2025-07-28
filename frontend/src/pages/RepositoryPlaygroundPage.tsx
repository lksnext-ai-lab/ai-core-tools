import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { apiService } from '../services/api';

interface SearchResult {
  content: string;
  metadata: {
    source: string;
    page?: number;
    [key: string]: any;
  };
  score: number;
}

const RepositoryPlaygroundPage: React.FC = () => {
  const { appId, repositoryId } = useParams<{ appId: string; repositoryId: string }>();
  const navigate = useNavigate();
  
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [repositoryName, setRepositoryName] = useState('');

  useEffect(() => {
    if (appId && repositoryId) {
      loadRepositoryInfo();
    }
  }, [appId, repositoryId]);

  const loadRepositoryInfo = async () => {
    try {
      const repository = await apiService.getRepository(parseInt(appId!), parseInt(repositoryId!));
      setRepositoryName(repository.name);
    } catch (err) {
      console.error('Error loading repository info:', err);
      setError('Failed to load repository information');
    }
  };

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!query.trim()) {
      setError('Please enter a search query');
      return;
    }

    try {
      setSearching(true);
      setError(null);
      setResults([]);

      // TODO: Implement repository search API call
      // For now, we'll show a placeholder
      
      // Simulate search results
      setTimeout(() => {
        setResults([
          {
            content: "This is a sample search result from the repository. The content would be extracted from uploaded documents.",
            metadata: {
              source: "sample-document.pdf",
              page: 1
            },
            score: 0.95
          },
          {
            content: "Another search result showing how the repository search functionality works.",
            metadata: {
              source: "another-document.docx"
            },
            score: 0.87
          }
        ]);
        setSearching(false);
      }, 1000);

    } catch (err) {
      console.error('Error searching repository:', err);
      setError('Failed to search repository');
      setSearching(false);
    }
  };

  const handleClearResults = () => {
    setResults([]);
    setQuery('');
    setError(null);
  };

  const formatScore = (score: number) => {
    return Math.round(score * 100);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
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
              onClick={() => navigate(`/apps/${appId}/repositories/${repositoryId}`)}
              className="text-gray-500 hover:text-gray-700 transition-colors"
            >
              ← Back
            </button>
            <h1 className="text-3xl font-bold text-gray-900">Repository Search</h1>
          </div>
          <p className="text-gray-600">
            Search within "{repositoryName}" repository
          </p>
        </div>
      </div>

      {/* Search Form */}
      <div className="bg-white border border-gray-200 rounded-lg p-6 mb-8">
        <form onSubmit={handleSearch} className="space-y-4">
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
                placeholder="Enter your search query..."
                className="flex-1 px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                disabled={searching}
              />
              <button
                type="submit"
                disabled={searching || !query.trim()}
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
        <div className="space-y-6">
          <div className="flex justify-between items-center">
            <h2 className="text-lg font-semibold text-gray-900">
              Search Results ({results.length})
            </h2>
            <button
              onClick={handleClearResults}
              className="text-gray-500 hover:text-gray-700 text-sm"
            >
              Clear Results
            </button>
          </div>

          <div className="space-y-4">
            {results.map((result, index) => (
              <div key={index} className="bg-white border border-gray-200 rounded-lg p-6">
                <div className="flex justify-between items-start mb-3">
                  <div className="flex items-center gap-2">
                    <span className="text-sm text-gray-500">📄</span>
                    <span className="text-sm font-medium text-gray-700">
                      {result.metadata.source}
                    </span>
                    {result.metadata.page && (
                      <span className="text-sm text-gray-500">
                        (Page {result.metadata.page})
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-gray-500">Relevance:</span>
                    <span className="text-sm font-medium text-green-600">
                      {formatScore(result.score)}%
                    </span>
                  </div>
                </div>
                
                <div className="bg-gray-50 rounded-lg p-4">
                  <p className="text-gray-800 leading-relaxed">
                    {result.content}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* No Results State */}
      {!searching && !loading && results.length === 0 && query && (
        <div className="text-center py-12">
          <div className="text-4xl text-gray-400 mb-4">🔍</div>
          <h3 className="text-lg font-medium text-gray-900 mb-2">No results found</h3>
          <p className="text-gray-600">
            Try adjusting your search query or check if the repository has documents.
          </p>
        </div>
      )}

      {/* Initial State */}
      {!searching && !loading && results.length === 0 && !query && (
        <div className="text-center py-12">
          <div className="text-4xl text-gray-400 mb-4">🔍</div>
          <h3 className="text-lg font-medium text-gray-900 mb-2">Ready to search</h3>
          <p className="text-gray-600">
            Enter a query above to search through the documents in this repository.
          </p>
        </div>
      )}
    </div>
  );
};

export default RepositoryPlaygroundPage; 