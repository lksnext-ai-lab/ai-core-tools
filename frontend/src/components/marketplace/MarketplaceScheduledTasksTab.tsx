import { useCallback, useEffect, useRef, useState } from 'react';
import { Search } from 'lucide-react';
import { apiService, type MarketplaceScheduledTask } from '../../services/api';
import { LoadingState } from '../ui/LoadingState';
import { ErrorState } from '../ui/ErrorState';
import { MarketplaceScheduledTaskCard } from './MarketplaceScheduledTaskCard';
import { Pagination } from './Pagination';
import ButtonApp from '../ui/ButtonApp';
import { FormField } from '../ui/FormField';
import { BackgroundImage, CardApp } from '../..';
import { SidePanel } from '../ui/SidePanel';
import MarketplaceScheduledTaskPage from '../../pages/MarketplaceScheduledTaskPage';
import { useTranslation } from 'react-i18next';

const PAGE_SIZE = 12;

/** Catalog of published scheduled tasks (read-only results). */
export function MarketplaceScheduledTasksTab() {
  const { t } = useTranslation('common');
  // Task shown in the right-hand detail panel (null = closed)
  const [selectedTaskId, setSelectedTaskId] = useState<number | null>(null);
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
      setError(err instanceof Error ? err.message : t('marketplacePage.loadScheduledTasksFailed'));
    } finally {
      setLoading(false);
    }
  }, [debouncedSearch, myAppsOnly, page, t]);

  useEffect(() => { void fetchCatalog(); }, [fetchCatalog]);

  const handleTaskClick = useCallback((taskId: number) => setSelectedTaskId(taskId), []);
  const handleClosePanel = useCallback(() => setSelectedTaskId(null), []);

  let content;
  if (loading) content = <LoadingState message={t('marketplacePage.loadingScheduledTasks')} />;
  else if (error) content = <ErrorState error={error} onRetry={fetchCatalog} />;
  else if (tasks.length === 0) {
    content = (
      <CardApp className="py-16 flex items-center justify-center">
        <BackgroundImage
                        icon={Search}
                        size={64}
                        iconSize={32}
                        variant="marron"
                      />
        <h3 className="mt-4 text-lg font-medium text-fg dark:text-fg-dark">{t('marketplacePage.noScheduledTasksFound')}</h3>
        <p className="mt-1 text-sm text-fg-secondary dark:text-fg-secondary-dark">
          {debouncedSearch || myAppsOnly ? t('marketplacePage.adjustFilters') : t('marketplacePage.noScheduledTasksPublished')}
        </p>
      </CardApp>
    );
  } else {
    content = (
      <>
        <p className="text-sm text-fg-secondary dark:text-fg-secondary-dark">
          {t('marketplacePage.taskCount', { count: total, shown: tasks.length })}
        </p>
        <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3">
          {tasks.map((task) => (
            <MarketplaceScheduledTaskCard key={task.id} task={task} onClick={handleTaskClick} />
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
          <span className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3 text-fg-faint dark:text-fg-faint-dark">
            <Search className="h-4 w-4" aria-hidden="true" />
          </span>
          <FormField
            id="scheduled-tasks-search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={t('marketplacePage.searchScheduledTasks')}
            ariaLabel={t('marketplacePage.searchScheduledTasks')}
            inputClassName="pl-10 pr-3"
          />
        </div>
        <ButtonApp
          label={t('marketplacePage.myApps')}
          variant="primary"
          size="control"
          ariaPressed={myAppsOnly}
          onClick={() => setMyAppsOnly((v) => !v)}
        />
      </div>
     
      {content}

      {/* Task detail side panel — fixed wrapper that starts below the 56px (h-14) app header */}
      {selectedTaskId !== null && (
        <div className="fixed inset-x-0 bottom-0 top-14 z-10 !mt-0">
          <SidePanel
            open
            side="right"
            onClose={handleClosePanel}
            title={t('marketplacePage.title')}
            widthClassName="w-[640px] max-w-full"
          >
            <MarketplaceScheduledTaskPage key={selectedTaskId} taskId={selectedTaskId} variant="panel" />
          </SidePanel>
        </div>
      )}
    </div>
  );
}
