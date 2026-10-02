import { useCallback, useEffect, useRef, useState } from 'react';
import { Search } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { apiService, type MarketplaceScheduledTask } from '../../services/api';
import { LoadingState } from '../ui/LoadingState';
import { ErrorState } from '../ui/ErrorState';
import { MarketplaceScheduledTaskCard } from './MarketplaceScheduledTaskCard';
import { Pagination } from './Pagination';
import ButtonApp from '../ui/ButtonApp';

const PAGE_SIZE = 12;

/** Catalog of published scheduled tasks (read-only results). */
export function MarketplaceScheduledTasksTab() {
  const navigate = useNavigate();
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [myAppsOnly, setMyAppsOnly] = useState(false);
  const [page, setPage] = useState(1);
  const [tasks, setTasks] = useState<MarketplaceScheduledTask[]>([]);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => { setDebouncedSearch(search); setPage(1); }, 300);
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current); };
  }, [search]);

  useEffect(() => { setPage(1); }, [myAppsOnly]);

  const fetchCatalog = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiService.getMarketplaceScheduledTasks({
        search: debouncedSearch || undefined, my_apps_only: myAppsOnly, page, page_size: PAGE_SIZE,
      });
      setTasks(data.tasks);
      setTotal(data.total);
      setTotalPages(data.total_pages);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load scheduled tasks');
    } finally {
      setLoading(false);
    }
  }, [debouncedSearch, myAppsOnly, page]);

  useEffect(() => { void fetchCatalog(); }, [fetchCatalog]);

  let content;
  if (loading) content = <LoadingState message="Loading scheduled tasks..." />;
  else if (error) content = <ErrorState error={error} onRetry={fetchCatalog} />;
  else if (tasks.length === 0) {
    content = (
      <div className="py-16 text-center">
        <Search className="mx-auto h-12 w-12 text-gray-300" aria-hidden="true" />
        <h3 className="mt-4 text-lg font-medium text-gray-900 dark:text-gray-100">No scheduled tasks found</h3>
        <p className="mt-1 text-sm text-gray-500">
          {debouncedSearch || myAppsOnly ? 'Try adjusting your search or filters.' : 'No scheduled tasks have been published yet.'}
        </p>
      </div>
    );
  } else {
    content = (
      <>
        <p className="text-sm text-gray-500">Showing {tasks.length} of {total} task{total === 1 ? '' : 's'}</p>
        <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3">
          {tasks.map((task) => (
            <MarketplaceScheduledTaskCard key={task.id} task={task} onClick={(id) => navigate(`/marketplace/scheduled-tasks/${id}`)} />
          ))}
        </div>
        {totalPages > 1 && <Pagination page={page} totalPages={totalPages} onPageChange={setPage} />}
      </>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col flex-wrap items-start gap-3 sm:flex-row sm:items-center">


        <div className="relative min-w-[200px] flex-1">
          <span className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3 text-gray-400">
            <Search className="h-4 w-4" aria-hidden="true" />
          </span>
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search scheduled tasks..."
            aria-label="Search scheduled tasks"
            className="w-full rounded-lg border border-gray-300 py-2 pl-10 pr-3 text-sm focus:border-gray-300 focus:outline-none focus:ring-2 focus:ring-gray-300"
          />
        </div>
        <ButtonApp
          label="My Apps"
          variant="primary"
          size="control"
          ariaPressed={myAppsOnly}
          onClick={() => setMyAppsOnly((v) => !v)}
        />
      </div>
     
      {content}
    </div>
  );
}
