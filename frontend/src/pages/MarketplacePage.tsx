import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Search } from 'lucide-react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { apiService } from '../services/api';
import { LoadingState } from '../components/ui/LoadingState';
import { ErrorState } from '../components/ui/ErrorState';
import { MarketplaceAgentCard } from '../components/marketplace/MarketplaceAgentCard';
import { MarketplaceScheduledTasksTab } from '../components/marketplace/MarketplaceScheduledTasksTab';
import { Pagination } from '../components/marketplace/Pagination';
import { MARKETPLACE_CATEGORIES } from '../types/marketplace';
import type {
  MarketplaceAgentCard as MarketplaceAgentCardType,
  MarketplaceCatalogParams,
} from '../types/marketplace';

const PAGE_SIZE = 12;

type SortOption = 'relevance' | 'newest' | 'alphabetical';

const SORT_OPTIONS: { value: SortOption; label: string }[] = [
  { value: 'relevance', label: 'Top Rated' },
  { value: 'newest', label: 'Newest' },
  { value: 'alphabetical', label: 'A–Z' },
];

type MarketplaceTab = 'agents' | 'tasks';

const TABS: { value: MarketplaceTab; label: string }[] = [
  { value: 'agents', label: 'Agents' },
  { value: 'tasks', label: 'Scheduled tasks' },
];

/**
 * Marketplace page — published agents (to chat with) and published scheduled tasks
 * (read-only results), each in its own tab.
 */
export default function MarketplacePage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const tab: MarketplaceTab = searchParams.get('tab') === 'tasks' ? 'tasks' : 'agents';

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">Marketplace</h1>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
          {tab === 'agents'
            ? 'Discover and chat with AI agents published across the platform.'
            : 'Browse the results of scheduled tasks published across the platform.'}
        </p>
      </div>
      <div role="tablist" aria-label="Marketplace sections" className="flex gap-1 border-b border-gray-200 dark:border-gray-700">
        {TABS.map((item) => (
          <button
            key={item.value}
            type="button"
            role="tab"
            aria-selected={tab === item.value}
            onClick={() => setSearchParams(item.value === 'agents' ? {} : { tab: item.value })}
            className={`-mb-px border-b-2 px-4 py-2 text-sm font-medium transition-colors ${
              tab === item.value
                ? 'border-blue-600 text-blue-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200'
            }`}
          >
            {item.label}
          </button>
        ))}
      </div>
      <div role="tabpanel">
        {tab === 'agents' ? <MarketplaceAgentsTab /> : <MarketplaceScheduledTasksTab />}
      </div>
    </div>
  );
}

/** Catalog of published agents — browse, search, and filter. */
function MarketplaceAgentsTab() {
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
          Showing {agents.length} of {total} agent{total === 1 ? '' : 's'}
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
      {/* Controls bar */}
      <div className="flex flex-col sm:flex-row flex-wrap gap-3 items-start sm:items-center">
        {/* Search */}
        <div className="relative flex-1 min-w-[200px]">
          <span className="absolute inset-y-0 left-0 flex items-center pl-3 text-gray-400 pointer-events-none">
            <Search className="w-4 h-4" />
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
      <Search className="w-12 h-12 text-gray-300 mx-auto" aria-hidden="true" />
      <h3 className="mt-4 text-lg font-medium text-gray-900">No agents found</h3>
      <p className="mt-1 text-sm text-gray-500">
        {hasFilters
          ? 'Try adjusting your search or filters.'
          : 'No agents have been published to the marketplace yet.'}
      </p>
    </div>
  );
}
