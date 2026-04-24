import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { AlertTriangle, ArrowLeft, Search, Info, Clock, History, Bot } from 'lucide-react';
import { apiService } from '../services/api';
import SearchControls, { type SearchControlsValue, DEFAULT_SEARCH_CONTROLS } from '../components/playground/SearchControls';
import SiloAPISnippets from '../components/playground/SiloAPISnippets';
import SearchFilters from '../components/playground/SearchFilters';
import type {
  SearchFilterMetadataField,
  SupportedDbType,
} from '../components/playground/SearchFilters';
import ResultCard, { type SearchResult } from '../components/playground/ResultCard';
import Modal from '../components/ui/Modal';

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

interface QueryHistoryEntry {
  query: string;
  controls: SearchControlsValue;
  filterMetadata?: Record<string, any>;
  minContentLength: number | null;
  maxContentLength: number | null;
  timestamp: number;
}

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
  const [minContentLength, setMinContentLength] = useState<number | null>(null);
  const [maxContentLength, setMaxContentLength] = useState<number | null>(null);
  const [searchControls, setSearchControls] = useState<SearchControlsValue>(DEFAULT_SEARCH_CONTROLS);

  // Multi-select (FR-4.1)
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [showBulkDeleteModal, setShowBulkDeleteModal] = useState(false);
  const [bulkDeleteLoading, setBulkDeleteLoading] = useState(false);

  // Single delete modal — replaces globalThis.confirm (FR-4.4)
  const [deleteTarget, setDeleteTarget] = useState<{ result: SearchResult; index: number } | null>(null);

  // Delete-by-filter (FR-4.2)
  const [showDeleteByFilterModal, setShowDeleteByFilterModal] = useState(false);
  const [deleteByFilterCount, setDeleteByFilterCount] = useState<number | null>(null);
  const [deleteByFilterLoading, setDeleteByFilterLoading] = useState(false);
  const [deleteByFilterConfirmName, setDeleteByFilterConfirmName] = useState('');

  const [showApiSnippets, setShowApiSnippets] = useState(false);

  // Reindex (FR-4.3)
  const [reindexLoading, setReindexLoading] = useState<string | null>(null);
  const [reindexMessage, setReindexMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  // Phase 6 observability
  const [queryHistory, setQueryHistory] = useState<QueryHistoryEntry[]>([]);
  const [showHistory, setShowHistory] = useState(false);
  const [lastClientMs, setLastClientMs] = useState<number | null>(null);
  const [lastServerMs, setLastServerMs] = useState<number | null>(null);
  const [showAgentShortcut, setShowAgentShortcut] = useState(false);
  const [appAgentsForSilo, setAppAgentsForSilo] = useState<Array<{ id: number; name: string }>>([]);

  // Load silo data
  useEffect(() => {
    if (appId && siloId) {
      void loadSilo();
    }
  }, [appId, siloId]);

  useEffect(() => {
    if (!siloId) return;
    try {
      const stored = localStorage.getItem(`silo_query_history_${siloId}`);
      if (stored) setQueryHistory(JSON.parse(stored) as QueryHistoryEntry[]);
    } catch { /* ignore */ }
  }, [siloId]);

  useEffect(() => {
    if (!appId || !siloId) return;
    apiService.getAgents(Number.parseInt(appId))
      .then((agents: unknown) => {
        const arr = (agents as Array<{ id: number; name: string; silo_id?: number | null }>) ?? [];
        setAppAgentsForSilo(arr.filter((a) => a.silo_id === Number.parseInt(siloId)));
      })
      .catch(() => { /* ignore */ });
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

  function saveToHistory(entry: QueryHistoryEntry) {
    if (!siloId) return;
    const key = `silo_query_history_${siloId}`;
    setQueryHistory((prev) => {
      const updated = [entry, ...prev].slice(0, 20);
      try { localStorage.setItem(key, JSON.stringify(updated)); } catch { /* quota */ }
      return updated;
    });
  }

  function deleteHistoryEntry(index: number) {
    if (!siloId) return;
    const key = `silo_query_history_${siloId}`;
    setQueryHistory((prev) => {
      const updated = prev.filter((_, i) => i !== index);
      try { localStorage.setItem(key, JSON.stringify(updated)); } catch { /* quota */ }
      return updated;
    });
  }

  function rerunHistoryEntry(entry: QueryHistoryEntry) {
    setSearchQuery(entry.query);
    setSearchControls(entry.controls);
    if (entry.filterMetadata !== undefined) handleFilterMetadataChange(entry.filterMetadata);
    setMinContentLength(entry.minContentLength);
    setMaxContentLength(entry.maxContentLength);
    setShowHistory(false);
  }

  async function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    
    if (!appId || !siloId) return;

    try {
      setIsSearching(true);
      setSearchError(null);
      setSearchResults([]);
      setHasSearched(true);
      const t0 = performance.now();
      const { data: response, serverMs } = await apiService.searchSiloDocumentsWithTiming(
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
          minContentLength: minContentLength ?? undefined,
          maxContentLength: maxContentLength ?? undefined,
        },
      );
      const clientMs = Math.round(performance.now() - t0);
      setLastClientMs(clientMs);
      setLastServerMs(serverMs);
      saveToHistory({
        query: searchQuery,
        controls: searchControls,
        filterMetadata,
        minContentLength,
        maxContentLength,
        timestamp: Date.now(),
      });
      
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

  function handleDeleteDocument(result: SearchResult, index: number) {
    if (!result.id) return;
    setDeleteTarget({ result, index });
  }

  async function handleDeleteConfirmed() {
    if (!deleteTarget || !appId || !siloId) return;
    const { result, index } = deleteTarget;
    try {
      setDeletingId(result.id ?? null);
      await apiService.deleteSiloDocuments(Number.parseInt(appId), Number.parseInt(siloId), [result.id!]);
      setSearchResults((prev) => prev.filter((_, i) => i !== index));
      setSelectedIds((prev) => { const s = new Set(prev); s.delete(result.id!); return s; });
      await loadSilo();
    } catch (err) {
      setSearchError(err instanceof Error ? err.message : 'Failed to delete document');
    } finally {
      setDeletingId(null);
      setDeleteTarget(null);
    }
  }

  function handleSelectResult(id: string, selected: boolean) {
    setSelectedIds((prev) => {
      const s = new Set(prev);
      if (selected) s.add(id); else s.delete(id);
      return s;
    });
  }

  async function handleBulkDelete() {
    if (!appId || !siloId) return;
    setBulkDeleteLoading(true);
    try {
      const ids = Array.from(selectedIds);
      await apiService.deleteSiloDocuments(Number.parseInt(appId), Number.parseInt(siloId), ids);
      setSearchResults((prev) => prev.filter((r) => !selectedIds.has(r.id ?? '')));
      setSelectedIds(new Set());
      setShowBulkDeleteModal(false);
      await loadSilo();
    } catch (err) {
      setSearchError(err instanceof Error ? err.message : 'Failed to delete documents');
    } finally {
      setBulkDeleteLoading(false);
    }
  }

  async function handleOpenDeleteByFilter() {
    if (!appId || !siloId) return;
    setDeleteByFilterCount(null);
    setDeleteByFilterConfirmName('');
    setDeleteByFilterLoading(true);
    setShowDeleteByFilterModal(true);
    try {
      const data = await apiService.countSiloDocuments(
        appId,
        siloId,
        filterMetadata,
        minContentLength,
        maxContentLength,
      );
      setDeleteByFilterCount((data as { count: number }).count);
    } catch {
      setDeleteByFilterCount(-1);
    } finally {
      setDeleteByFilterLoading(false);
    }
  }

  async function handleDeleteByFilterConfirmed() {
    if (!appId || !siloId || !silo) return;
    setBulkDeleteLoading(true);
    try {
      const searchData = await apiService.searchSiloDocuments(
        Number.parseInt(appId),
        Number.parseInt(siloId),
        ' ',
        200,
        filterMetadata,
        {
          minContentLength: minContentLength ?? undefined,
          maxContentLength: maxContentLength ?? undefined,
        },
      );
      const ids: string[] = ((searchData as { results: Array<{ id?: string; metadata?: { _id?: string } }> }).results ?? [])
        .map((r) => r.id ?? (r.metadata?._id as string | undefined) ?? '')
        .filter(Boolean);
      if (ids.length > 0) {
        await apiService.deleteSiloDocuments(Number.parseInt(appId), Number.parseInt(siloId), ids);
        setSearchResults((prev) => prev.filter((r) => !ids.includes(r.id ?? '')));
      }
      setShowDeleteByFilterModal(false);
      setDeleteByFilterConfirmName('');
      await loadSilo();
    } catch (err) {
      setSearchError(err instanceof Error ? err.message : 'Failed to delete documents by filter');
    } finally {
      setBulkDeleteLoading(false);
    }
  }

  async function handleReindex(resourceId: string) {
    if (!appId || !siloId) return;
    setReindexLoading(resourceId);
    setReindexMessage(null);
    try {
      await apiService.reindexSiloResource(appId, siloId, resourceId);
      setReindexMessage({ type: 'success', text: `Resource ${resourceId} reindexed successfully.` });
    } catch (err) {
      setReindexMessage({ type: 'error', text: err instanceof Error ? err.message : 'Reindex failed' });
    } finally {
      setReindexLoading(null);
      setTimeout(() => setReindexMessage(null), 4000);
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

          {/* Content-length filter */}
          <div className="flex items-center gap-3 flex-wrap">
            <span className="text-sm font-medium text-gray-700">Content length (chars):</span>
            <div className="flex items-center gap-1">
              <label htmlFor="minContentLength" className="text-xs text-gray-500">Min</label>
              <input
                type="number"
                id="minContentLength"
                min={0}
                placeholder="–"
                value={minContentLength ?? ''}
                onChange={(e) => setMinContentLength(e.target.value === '' ? null : Number(e.target.value))}
                className="w-20 px-2 py-1 text-sm border border-gray-300 rounded focus:outline-none focus:ring-1 focus:ring-yellow-400"
                disabled={isSearching}
              />
            </div>
            <div className="flex items-center gap-1">
              <label htmlFor="maxContentLength" className="text-xs text-gray-500">Max</label>
              <input
                type="number"
                id="maxContentLength"
                min={0}
                placeholder="–"
                value={maxContentLength ?? ''}
                onChange={(e) => setMaxContentLength(e.target.value === '' ? null : Number(e.target.value))}
                className="w-20 px-2 py-1 text-sm border border-gray-300 rounded focus:outline-none focus:ring-1 focus:ring-yellow-400"
                disabled={isSearching}
              />
            </div>
            {(minContentLength != null || maxContentLength != null) && (
              <button
                type="button"
                onClick={() => { setMinContentLength(null); setMaxContentLength(null); }}
                className="text-xs text-gray-400 hover:text-gray-600 underline"
              >
                Clear
              </button>
            )}
          </div>

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

        {/* Phase 6 observability toolbar */}
        {(lastClientMs !== null || queryHistory.length > 0 || appAgentsForSilo.length > 0) && (
          <div className="flex flex-wrap items-center gap-3 mt-3">
            {lastClientMs !== null && (
              <div className="flex items-center gap-1.5 text-xs text-gray-500">
                <Clock className="w-3.5 h-3.5" />
                <span>Client: <strong>{lastClientMs} ms</strong></span>
                {lastServerMs !== null && (
                  <span className="text-gray-400">· Server: <strong>{lastServerMs} ms</strong></span>
                )}
              </div>
            )}

            {queryHistory.length > 0 && (
              <button
                type="button"
                onClick={() => setShowHistory((v) => !v)}
                className="flex items-center gap-1 text-xs text-gray-500 hover:text-gray-700"
              >
                <History className="w-3.5 h-3.5" />
                {showHistory ? 'Hide history' : `History (${queryHistory.length})`}
              </button>
            )}

            {appAgentsForSilo.length > 0 && (
              <div className="relative">
                <button
                  type="button"
                  onClick={() => setShowAgentShortcut((v) => !v)}
                  className="flex items-center gap-1 text-xs text-gray-500 hover:text-gray-700 border border-gray-200 rounded px-2 py-1"
                >
                  <Bot className="w-3.5 h-3.5" />
                  Test against agent
                </button>
                {showAgentShortcut && (
                  <div className="absolute left-0 top-full mt-1 z-10 bg-white border border-gray-200 rounded shadow-md min-w-44">
                    {appAgentsForSilo.map((agent) => (
                      <button
                        key={agent.id}
                        type="button"
                        onClick={() => {
                          const qs = searchQuery ? `?q=${encodeURIComponent(searchQuery)}` : '';
                          navigate(`/apps/${appId}/agents/${agent.id}/playground${qs}`);
                        }}
                        className="block w-full text-left px-3 py-2 text-sm hover:bg-gray-50 truncate"
                      >
                        {agent.name}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {showHistory && queryHistory.length > 0 && (
          <div className="border border-gray-200 rounded-lg bg-gray-50 p-3 space-y-1 mt-3">
            <p className="text-xs font-medium text-gray-600 mb-2">Recent queries</p>
            {queryHistory.map((entry, i) => (
              <div key={entry.timestamp} className="flex items-center gap-2 text-sm">
                <button
                  type="button"
                  onClick={() => rerunHistoryEntry(entry)}
                  className="flex-1 text-left truncate text-gray-800 hover:text-yellow-700 hover:underline"
                  title={entry.query}
                >
                  {entry.query || '(empty query)'}
                </button>
                <span className="text-xs text-gray-400 shrink-0">
                  {new Date(entry.timestamp).toLocaleTimeString()}
                </span>
                <button
                  type="button"
                  onClick={() => deleteHistoryEntry(i)}
                  className="text-gray-300 hover:text-red-400 shrink-0 text-base leading-none"
                  title="Remove"
                >
                  ×
                </button>
              </div>
            ))}
          </div>
        )}

        {/* API snippet toggle + panel */}
        <div className="mt-3">
          <button
            type="button"
            onClick={() => setShowApiSnippets((v) => !v)}
            className="text-sm text-gray-500 hover:text-gray-700 underline"
          >
            {showApiSnippets ? 'Hide API snippet' : 'Show as API call'}
          </button>
          {showApiSnippets && (
            <div className="mt-3">
              <SiloAPISnippets
                appId={appId ?? ''}
                siloId={siloId ?? ''}
                siloName={silo?.name}
                query={searchQuery}
                limit={searchControls.limit}
                filterMetadata={filterMetadata as Record<string, unknown> | undefined}
                searchType={searchControls.searchType}
                scoreThreshold={searchControls.searchType === 'similarity_score_threshold' ? searchControls.scoreThreshold : undefined}
                fetchK={searchControls.searchType === 'mmr' ? searchControls.fetchK : undefined}
                lambdaMult={searchControls.searchType === 'mmr' ? searchControls.lambdaMult : undefined}
              />
            </div>
          )}
        </div>

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

          {/* Curator toolbar */}
          <div className="flex flex-wrap items-center gap-3 mb-4 py-2 px-3 bg-gray-50 border border-gray-200 rounded-lg text-sm">
            <label className="flex items-center gap-1.5 cursor-pointer text-gray-600 select-none">
              <input
                type="checkbox"
                checked={selectedIds.size > 0 && selectedIds.size === searchResults.length}
                onChange={(e) => {
                  if (e.target.checked) {
                    setSelectedIds(new Set(searchResults.map((r) => r.id ?? '').filter(Boolean)));
                  } else {
                    setSelectedIds(new Set());
                  }
                }}
                className="accent-amber-500"
              />
              {selectedIds.size > 0 ? `${selectedIds.size} selected` : 'Select all'}
            </label>
            {selectedIds.size > 0 && (
              <button
                onClick={() => setShowBulkDeleteModal(true)}
                className="px-3 py-1 bg-red-600 text-white rounded hover:bg-red-700 text-xs font-medium"
              >
                Delete selected ({selectedIds.size})
              </button>
            )}
            {filterMetadata && Object.keys(filterMetadata).length > 0 && (
              <button
                onClick={handleOpenDeleteByFilter}
                className="px-3 py-1 border border-red-400 text-red-600 rounded hover:bg-red-50 text-xs font-medium"
              >
                Delete by filter…
              </button>
            )}
            {reindexMessage && (
              <span className={`ml-auto text-xs font-medium ${reindexMessage.type === 'success' ? 'text-green-600' : 'text-red-600'}`}>
                {reindexMessage.text}
              </span>
            )}
          </div>
          
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
                isSelected={selectedIds.has(result.id ?? '')}
                onSelect={handleSelectResult}
                onReindex={reindexLoading === null ? handleReindex : undefined}
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

      {/* Single delete confirmation modal */}
      <Modal
        isOpen={deleteTarget !== null}
        onClose={() => setDeleteTarget(null)}
        title="Delete document"
        size="small"
      >
        <p className="text-sm text-gray-700 mb-4">
          Are you sure you want to delete this document from the silo? This action cannot be undone.
        </p>
        <div className="flex gap-2 justify-end">
          <button
            onClick={() => setDeleteTarget(null)}
            className="px-4 py-2 text-sm border border-gray-300 rounded hover:bg-gray-50"
          >
            Cancel
          </button>
          <button
            onClick={() => void handleDeleteConfirmed()}
            className="px-4 py-2 text-sm bg-red-600 text-white rounded hover:bg-red-700"
          >
            Delete
          </button>
        </div>
      </Modal>

      {/* Bulk delete confirmation modal */}
      <Modal
        isOpen={showBulkDeleteModal}
        onClose={() => setShowBulkDeleteModal(false)}
        title={`Delete ${selectedIds.size} document(s)`}
        size="small"
      >
        <p className="text-sm text-gray-700 mb-4">
          You are about to permanently delete <strong>{selectedIds.size}</strong> document(s) from the silo. This action cannot be undone.
        </p>
        <div className="flex gap-2 justify-end">
          <button
            onClick={() => setShowBulkDeleteModal(false)}
            className="px-4 py-2 text-sm border border-gray-300 rounded hover:bg-gray-50"
          >
            Cancel
          </button>
          <button
            onClick={() => void handleBulkDelete()}
            disabled={bulkDeleteLoading}
            className="px-4 py-2 text-sm bg-red-600 text-white rounded hover:bg-red-700 disabled:opacity-50"
          >
            {bulkDeleteLoading ? 'Deleting…' : `Delete ${selectedIds.size}`}
          </button>
        </div>
      </Modal>

      {/* Delete by filter modal */}
      <Modal
        isOpen={showDeleteByFilterModal}
        onClose={() => { setShowDeleteByFilterModal(false); setDeleteByFilterConfirmName(''); }}
        title="Delete by current filter"
        size="small"
      >
        {deleteByFilterLoading ? (
          <p className="text-sm text-gray-600">Counting matching documents…</p>
        ) : deleteByFilterCount === -1 ? (
          <p className="text-sm text-red-600">Could not retrieve count. Check filters and try again.</p>
        ) : (
          <>
            <p className="text-sm text-gray-700 mb-3">
              This will permanently delete{' '}
              <strong>{deleteByFilterCount ?? '…'}</strong> document(s) matching the current filter.
              This action cannot be undone.
            </p>
            <p className="text-sm text-gray-600 mb-2">
              Type the silo name <strong>{silo.name}</strong> to confirm:
            </p>
            <input
              type="text"
              value={deleteByFilterConfirmName}
              onChange={(e) => setDeleteByFilterConfirmName(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded text-sm mb-4 focus:outline-none focus:ring-2 focus:ring-red-400"
              placeholder={silo.name}
            />
            <div className="flex gap-2 justify-end">
              <button
                onClick={() => { setShowDeleteByFilterModal(false); setDeleteByFilterConfirmName(''); }}
                className="px-4 py-2 text-sm border border-gray-300 rounded hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                onClick={() => void handleDeleteByFilterConfirmed()}
                disabled={deleteByFilterConfirmName !== silo.name || bulkDeleteLoading}
                className="px-4 py-2 text-sm bg-red-600 text-white rounded hover:bg-red-700 disabled:opacity-50"
              >
                {bulkDeleteLoading ? 'Deleting…' : 'Delete all matching'}
              </button>
            </div>
          </>
        )}
      </Modal>
    </div>
  );
}

export default SiloPlaygroundPage;