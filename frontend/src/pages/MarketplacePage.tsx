import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { apiService } from '../services/api';
import { LoadingState } from '../components/ui/LoadingState';
import { ErrorState } from '../components/ui/ErrorState';
import { MarketplaceAgentCard } from '../components/marketplace/MarketplaceAgentCard';
import { MARKETPLACE_CATEGORIES } from '../types/marketplace';
import type {
  MarketplaceAgentCard as MarketplaceAgentCardType,
  MarketplaceCatalogParams,
} from '../types/marketplace';

const PAGE_SIZE = 12;

type SortOption = 'relevance' | 'newest' | 'alphabetical';

const SORT_OPTIONS: { value: SortOption; label: string }[] = [
  { value: 'relevance', label: 'Relevance' },
  { value: 'newest', label: 'Newest' },
  { value: 'alphabetical', label: 'A–Z' },
];

/**
 * Marketplace catalog page — browse, search, and filter published agents.
 */
export default function MarketplacePage() {
  const navigate = useNavigate();

  // Filter / pagination state
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [category, setCategory] = useState('');
  const [sortBy, setSortBy] = useState<SortOption>('relevance');
  const [myAppsOnly, setMyAppsOnly] = useState(false);
  const [page, setPage] = useState(1);

  // Data state
  const [agents, setAgents] = useState<MarketplaceAgentCardType[]>([]);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Debounce search input (300ms)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      setDebouncedSearch(search);
      setPage(1); // reset to first page on new search
    }, 300);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [search]);

  // Reset page when filters change
  useEffect(() => {
    setPage(1);
  }, [category, sortBy, myAppsOnly]);

  // Fetch catalog
  const fetchCatalog = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params: MarketplaceCatalogParams = {
        page,
        page_size: PAGE_SIZE,
        sort_by: sortBy,
      };
      if (debouncedSearch) params.search = debouncedSearch;
      if (category) params.category = category;
      if (myAppsOnly) params.my_apps_only = true;

      const data = await apiService.getMarketplaceCatalog(params);
      setAgents(data.agents);
      setTotal(data.total);
      setTotalPages(data.total_pages);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load marketplace');
    } finally {
      setLoading(false);
    }
  }, [debouncedSearch, category, sortBy, myAppsOnly, page]);

  useEffect(() => {
    fetchCatalog();
  }, [fetchCatalog]);

  const handleAgentClick = useCallback(
    (agentId: number) => navigate(`/marketplace/agents/${agentId}`),
    [navigate],
  );

  function renderContent() {
    if (loading) {
      return <LoadingState message="Loading marketplace..." />;
    }
    if (error) {
      return <ErrorState error={error} onRetry={fetchCatalog} />;
    }
    if (agents.length === 0) {
      return <EmptyState search={debouncedSearch} category={category} />;
    }
    return (
      <>
        <p className="text-sm text-gray-500">
          Showing {agents.length} of {total} agent{total !== 1 ? 's' : ''}
        </p>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {agents.map((agent) => (
            <MarketplaceAgentCard
              key={agent.agent_id}
              agent={agent}
              onClick={handleAgentClick}
            />
          ))}
        </div>
        {totalPages > 1 && (
          <Pagination page={page} totalPages={totalPages} onPageChange={setPage} />
        )}
      </>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Agent Marketplace</h1>
        <p className="mt-1 text-sm text-gray-500">
          Discover and chat with AI agents published across the platform.
        </p>
      </div>

      {/* Controls bar */}
      <div className="flex flex-col sm:flex-row flex-wrap gap-3 items-start sm:items-center">
        {/* Search */}
        <div className="relative flex-1 min-w-[200px]">
          <span className="absolute inset-y-0 left-0 flex items-center pl-3 text-gray-400 pointer-events-none">
            🔍
          </span>
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search agents..."
            className="w-full pl-10 pr-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
          />
        </div>

        {/* Category */}
        <select
          value={category}
          onChange={(e) => setCategory(e.target.value)}
          className="border border-gray-300 rounded-lg text-sm py-2 px-3 focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          <option value="">All Categories</option>
          {MARKETPLACE_CATEGORIES.map((cat) => (
            <option key={cat} value={cat}>
              {cat}
            </option>
          ))}
        </select>

        {/* Sort */}
        <select
          value={sortBy}
          onChange={(e) => setSortBy(e.target.value as SortOption)}
          className="border border-gray-300 rounded-lg text-sm py-2 px-3 focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          {SORT_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>

        {/* My Apps toggle */}
        <button
          type="button"
          onClick={() => setMyAppsOnly((v) => !v)}
          className={`text-sm py-2 px-4 rounded-lg border transition-colors ${
            myAppsOnly
              ? 'bg-blue-600 text-white border-blue-600'
              : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50'
          }`}
        >
          My Apps
        </button>
      </div>

      {/* Content */}
      {renderContent()}
    </div>
  );
}

/* ========== Sub-components ========== */

interface EmptyStateProps {
  readonly search: string;
  readonly category: string;
}

function EmptyState({ search, category }: EmptyStateProps) {
  const hasFilters = Boolean(search || category);
  return (
    <div className="text-center py-16">
      <span className="text-5xl" aria-hidden="true">
        🔎
      </span>
      <h3 className="mt-4 text-lg font-medium text-gray-900">No agents found</h3>
      <p className="mt-1 text-sm text-gray-500">
        {hasFilters
          ? 'Try adjusting your search or filters.'
          : 'No agents have been published to the marketplace yet.'}
      </p>
    </div>
  );
}

interface PaginationProps {
  readonly page: number;
  readonly totalPages: number;
  readonly onPageChange: (page: number) => void;
}

function Pagination({ page, totalPages, onPageChange }: PaginationProps) {
  // Build a window of page numbers around the current page
  const pages: number[] = [];
  const start = Math.max(1, page - 2);
  const end = Math.min(totalPages, page + 2);
  for (let i = start; i <= end; i++) {
    pages.push(i);
  }

  return (
    <nav className="flex items-center justify-center gap-1 mt-4" aria-label="Pagination">
      <button
        type="button"
        disabled={page <= 1}
        onClick={() => onPageChange(page - 1)}
        className="px-3 py-2 text-sm rounded-lg border border-gray-300 disabled:opacity-40 disabled:cursor-not-allowed hover:bg-gray-50"
      >
        Previous
      </button>

      {start > 1 && (
        <>
          <button
            type="button"
            onClick={() => onPageChange(1)}
            className="px-3 py-2 text-sm rounded-lg border border-gray-300 hover:bg-gray-50"
          >
            1
          </button>
          {start > 2 && <span className="px-2 text-gray-400">…</span>}
        </>
      )}

      {pages.map((p) => (
        <button
          key={p}
          type="button"
          onClick={() => onPageChange(p)}
          className={`px-3 py-2 text-sm rounded-lg border ${
            p === page
              ? 'bg-blue-600 text-white border-blue-600'
              : 'border-gray-300 hover:bg-gray-50'
          }`}
        >
          {p}
        </button>
      ))}

      {end < totalPages && (
        <>
          {end < totalPages - 1 && <span className="px-2 text-gray-400">…</span>}
          <button
            type="button"
            onClick={() => onPageChange(totalPages)}
            className="px-3 py-2 text-sm rounded-lg border border-gray-300 hover:bg-gray-50"
          >
            {totalPages}
          </button>
        </>
      )}

      <button
        type="button"
        disabled={page >= totalPages}
        onClick={() => onPageChange(page + 1)}
        className="px-3 py-2 text-sm rounded-lg border border-gray-300 disabled:opacity-40 disabled:cursor-not-allowed hover:bg-gray-50"
      >
        Next
      </button>
    </nav>
  );
}
