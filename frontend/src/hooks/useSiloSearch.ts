import { useState, useEffect, useCallback } from 'react';
import type { FormEvent, Dispatch, SetStateAction } from 'react';
import { useNavigate } from 'react-router-dom';
import { apiService } from '../services/api';
import { DEFAULT_SEARCH_CONTROLS } from '../components/playground/SearchControls';
import type { SearchControlsValue } from '../components/playground/SearchControls';
import type { SearchResult } from '../components/playground/ResultCard';
import type { SearchFilterMetadataField } from '../components/playground/SearchFilters';

// ---------------------------------------------------------------------------
// Exported types
// ---------------------------------------------------------------------------

export interface Silo {
  silo_id: number;
  name: string;
  type?: string;
  created_at?: string;
  docs_count: number;
  metadata_fields?: SearchFilterMetadataField[];
}

export interface QueryHistoryEntry {
  query: string;
  controls: SearchControlsValue;
  filterMetadata?: Record<string, any>;
  minContentLength: number | null;
  maxContentLength: number | null;
  timestamp: number;
}

export interface PanelState {
  query: string;
  results: SearchResult[];
  isSearching: boolean;
  error: string | null;
  clientMs: number | null;
}

export interface SiloSearchState {
  // Silo data
  silo: Silo | null;
  loading: boolean;
  error: string | null;
  systemDBConfig: string;

  // Search
  searchQuery: string;
  setSearchQuery: Dispatch<SetStateAction<string>>;
  searchResults: SearchResult[];
  isSearching: boolean;
  searchError: string | null;
  hasSearched: boolean;

  // Filters
  filterMetadata: Record<string, any> | undefined;
  minContentLength: number | null;
  setMinContentLength: Dispatch<SetStateAction<number | null>>;
  maxContentLength: number | null;
  setMaxContentLength: Dispatch<SetStateAction<number | null>>;
  searchControls: SearchControlsValue;
  setSearchControls: Dispatch<SetStateAction<SearchControlsValue>>;

  // Selection / delete
  selectedIds: Set<string>;
  setSelectedIds: Dispatch<SetStateAction<Set<string>>>;
  deletingId: string | null;
  showBulkDeleteModal: boolean;
  setShowBulkDeleteModal: Dispatch<SetStateAction<boolean>>;
  bulkDeleteLoading: boolean;
  deleteTarget: { result: SearchResult; index: number } | null;
  setDeleteTarget: Dispatch<SetStateAction<{ result: SearchResult; index: number } | null>>;

  // Delete by filter
  showDeleteByFilterModal: boolean;
  setShowDeleteByFilterModal: Dispatch<SetStateAction<boolean>>;
  deleteByFilterCount: number | null;
  deleteByFilterLoading: boolean;
  deleteByFilterConfirmName: string;
  setDeleteByFilterConfirmName: Dispatch<SetStateAction<string>>;

  // API snippets
  showApiSnippets: boolean;
  setShowApiSnippets: Dispatch<SetStateAction<boolean>>;

  // Reindex
  reindexLoading: string | null;
  reindexMessage: { type: 'success' | 'error'; text: string } | null;

  // Observability / history
  queryHistory: QueryHistoryEntry[];
  showHistory: boolean;
  setShowHistory: Dispatch<SetStateAction<boolean>>;
  lastClientMs: number | null;
  lastServerMs: number | null;
  showAgentShortcut: boolean;
  setShowAgentShortcut: Dispatch<SetStateAction<boolean>>;
  appAgentsForSilo: Array<{ id: number; name: string }>;

  // A/B compare mode
  compareMode: boolean;
  setCompareMode: Dispatch<SetStateAction<boolean>>;
  panelA: PanelState;
  setPanelA: Dispatch<SetStateAction<PanelState>>;
  panelB: PanelState;
  setPanelB: Dispatch<SetStateAction<PanelState>>;

  // Derived values
  maxScore: number;
  sharedIds: Set<string>;

  // Handlers
  handleSearch: (e: FormEvent) => Promise<void>;
  handleBack: () => void;
  handleFilterMetadataChange: (metadata: Record<string, any> | undefined) => void;
  handleDeleteDocument: (result: SearchResult, index: number) => void;
  handleDeleteConfirmed: () => Promise<void>;
  handleSelectResult: (id: string, selected: boolean) => void;
  handleBulkDelete: () => Promise<void>;
  handleOpenDeleteByFilter: () => Promise<void>;
  handleDeleteByFilterConfirmed: () => Promise<void>;
  handleReindex: (resourceId: string) => Promise<void>;
  searchPanel: (panelQuery: string, setter: Dispatch<SetStateAction<PanelState>>) => Promise<void>;
  deleteHistoryEntry: (index: number) => void;
  rerunHistoryEntry: (entry: QueryHistoryEntry) => void;
  handleNavigateToAgent: (agentId: number) => void;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const DEFAULT_DB_TYPE = 'PGVECTOR';

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useSiloSearch(
  appId: string | undefined,
  siloId: string | undefined,
): SiloSearchState {
  const navigate = useNavigate();

  const [systemDBConfig, setSystemDBConfig] = useState('');
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

  // Single delete modal (FR-4.4)
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

  // A/B compare mode (FR-6.2)
  const [compareMode, setCompareMode] = useState(false);
  const [panelA, setPanelA] = useState<PanelState>({ query: '', results: [], isSearching: false, error: null, clientMs: null });
  const [panelB, setPanelB] = useState<PanelState>({ query: '', results: [], isSearching: false, error: null, clientMs: null });

  // -------------------------------------------------------------------------
  // Effects
  // -------------------------------------------------------------------------

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

  // -------------------------------------------------------------------------
  // Internal helpers
  // -------------------------------------------------------------------------

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

  // -------------------------------------------------------------------------
  // Exported handlers
  // -------------------------------------------------------------------------

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

  async function handleSearch(e: FormEvent) {
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
        id: result.metadata?._id as string | undefined,
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

  async function searchPanel(
    panelQuery: string,
    setter: Dispatch<SetStateAction<PanelState>>,
  ) {
    if (!appId || !siloId) return;
    setter((p) => ({ ...p, isSearching: true, error: null }));
    try {
      const t0 = performance.now();
      const { data, serverMs: _serverMs } = await apiService.searchSiloDocumentsWithTiming(
        Number.parseInt(appId),
        Number.parseInt(siloId),
        panelQuery,
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
      const resultsWithIds = ((data.results ?? []) as SearchResult[]).map((r: SearchResult) => ({
        ...r,
        id: r.metadata?._id as string | undefined,
      }));
      setter({ query: panelQuery, results: resultsWithIds, isSearching: false, error: null, clientMs });
    } catch (err) {
      setter((p) => ({ ...p, isSearching: false, error: err instanceof Error ? err.message : 'Search failed' }));
    }
  }

  function handleNavigateToAgent(agentId: number) {
    const qs = searchQuery ? `?q=${encodeURIComponent(searchQuery)}` : '';
    navigate(`/apps/${appId}/agents/${agentId}/playground${qs}`);
  }

  // -------------------------------------------------------------------------
  // Derived values
  // -------------------------------------------------------------------------

  const maxScore =
    searchResults.length > 0
      ? Math.max(...searchResults.map((r) => r.score ?? 0))
      : 0;

  const sharedIds = compareMode
    ? new Set(
        panelA.results
          .map((r) => r.id)
          .filter((id): id is string => Boolean(id) && panelB.results.some((r) => r.id === id)),
      )
    : new Set<string>();

  // -------------------------------------------------------------------------
  // Return
  // -------------------------------------------------------------------------

  return {
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
  };
}
