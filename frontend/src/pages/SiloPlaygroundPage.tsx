import type { Dispatch, SetStateAction } from 'react';
import { useParams } from 'react-router-dom';
import { AlertTriangle, ArrowLeft, Search, Info, Clock, History, Bot, SplitSquareHorizontal } from 'lucide-react';
import SearchControls from '../components/playground/SearchControls';
import SiloAPISnippets from '../components/playground/SiloAPISnippets';
import SearchFilters from '../components/playground/SearchFilters';
import ResultCard from '../components/playground/ResultCard';
import Modal from '../components/ui/Modal';
import { useSiloSearch } from '../hooks/useSiloSearch';
import type { PanelState } from '../hooks/useSiloSearch';

function SiloPlaygroundPage() {
  const { appId, siloId } = useParams();
  const {
    silo,
    loading,
    error,
    systemDBConfig,
    searchQuery,
    setSearchQuery,
    searchResults,
    isSearching,
    searchError,
    hasSearched,
    filterMetadata,
    minContentLength,
    setMinContentLength,
    maxContentLength,
    setMaxContentLength,
    searchControls,
    setSearchControls,
    selectedIds,
    setSelectedIds,
    deletingId,
    showBulkDeleteModal,
    setShowBulkDeleteModal,
    bulkDeleteLoading,
    deleteTarget,
    setDeleteTarget,
    showDeleteByFilterModal,
    setShowDeleteByFilterModal,
    deleteByFilterCount,
    deleteByFilterLoading,
    deleteByFilterConfirmName,
    setDeleteByFilterConfirmName,
    showApiSnippets,
    setShowApiSnippets,
    reindexLoading,
    reindexMessage,
    queryHistory,
    showHistory,
    setShowHistory,
    lastClientMs,
    lastServerMs,
    showAgentShortcut,
    setShowAgentShortcut,
    appAgentsForSilo,
    compareMode,
    setCompareMode,
    panelA,
    setPanelA,
    panelB,
    setPanelB,
    maxScore,
    sharedIds,
    handleSearch,
    handleBack,
    handleFilterMetadataChange,
    handleDeleteDocument,
    handleDeleteConfirmed,
    handleSelectResult,
    handleBulkDelete,
    handleOpenDeleteByFilter,
    handleDeleteByFilterConfirmed,
    handleReindex,
    searchPanel,
    deleteHistoryEntry,
    rerunHistoryEntry,
    handleNavigateToAgent,
  } = useSiloSearch(appId, siloId);

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

  function renderComparePanel(
    label: string,
    panel: PanelState,
    setter: Dispatch<SetStateAction<PanelState>>,
  ) {
    const panelMax = panel.results.length > 0 ? Math.max(...panel.results.map((r) => r.score ?? 0)) : 0;
    return (
      <div className="bg-white shadow rounded-lg p-4 flex flex-col gap-3">
        <div className="flex items-center gap-2">
          <span className="text-xs font-bold bg-yellow-100 text-yellow-800 px-2 py-0.5 rounded">
            Panel {label}
          </span>
          {panel.clientMs !== null && (
            <span className="text-xs text-gray-400">{panel.clientMs} ms</span>
          )}
        </div>

        <div className="flex gap-2">
          <input
            type="text"
            value={panel.query}
            onChange={(e) => setter((p) => ({ ...p, query: e.target.value }))}
            onKeyDown={(e) => { if (e.key === 'Enter') void searchPanel(panel.query, setter); }}
            placeholder="Enter query…"
            className="flex-1 px-3 py-1.5 text-sm border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-yellow-500"
            disabled={panel.isSearching}
          />
          <button
            type="button"
            onClick={() => void searchPanel(panel.query, setter)}
            disabled={panel.isSearching}
            className="px-3 py-1.5 text-sm bg-yellow-600 hover:bg-yellow-700 disabled:bg-yellow-400 text-white rounded flex items-center gap-1"
          >
            {panel.isSearching && (
              <div className="animate-spin rounded-full h-3 w-3 border-b-2 border-white" />
            )}
            Search
          </button>
        </div>

        {panel.error && <p className="text-xs text-red-600">{panel.error}</p>}

        {panel.results.length === 0 && !panel.isSearching && (
          <p className="text-xs text-gray-400 italic">No results yet. Run a search.</p>
        )}

        <div className="space-y-2 overflow-y-auto max-h-[60vh]">
          {panel.results.map((result, idx) => {
            const isShared = result.id ? sharedIds.has(result.id) : false;
            return (
              <div key={result.id ?? idx} className={isShared ? 'ring-2 ring-yellow-400 rounded-lg' : ''}>
                <ResultCard
                  result={result}
                  index={idx}
                  maxScore={panelMax}
                  appId={appId ?? ''}
                  siloId={siloId ?? ''}
                />
              </div>
            );
          })}
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
                        onClick={() => handleNavigateToAgent(agent.id)}
                        className="block w-full text-left px-3 py-2 text-sm hover:bg-gray-50 truncate"
                      >
                        {agent.name}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}

            <button
              type="button"
              onClick={() => setCompareMode((v) => !v)}
              className={`flex items-center gap-1 text-xs border rounded px-2 py-1 ${
                compareMode
                  ? 'border-yellow-500 text-yellow-700 bg-yellow-50'
                  : 'border-gray-200 text-gray-500 hover:text-gray-700'
              }`}
            >
              <SplitSquareHorizontal className="w-3.5 h-3.5" />
              {compareMode ? 'Exit compare' : 'Compare'}
            </button>
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

      {/* A/B compare mode */}
      {compareMode && (
        <div className="grid grid-cols-2 gap-4">
          {renderComparePanel('A', panelA, setPanelA)}
          {renderComparePanel('B', panelB, setPanelB)}
        </div>
      )}

      {/* Search Results (single panel) */}
      {!compareMode && searchResults.length > 0 && (
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
      {!compareMode && !isSearching && searchResults.length === 0 && hasSearched && !searchError && (
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