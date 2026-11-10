import { useTranslation } from 'react-i18next';

interface TablePaginationProps {
  page: number;
  totalPages: number;
  totalItems?: number;
  onPageChange: (page: number) => void;
}

export default function TablePagination({ page, totalPages, totalItems, onPageChange }: Readonly<TablePaginationProps>) {
  const { t } = useTranslation('common');

  if (totalPages <= 1) return null;

  const pageLabel = t('pagination.pageOf', { page, totalPages });

  return (
    <div className="mt-4 flex min-w-0 items-center gap-4">
      <nav
        className="flex min-w-0 flex-1 items-center justify-center gap-1 overflow-x-auto whitespace-nowrap"
        aria-label={t('pagination.ariaLabel')}
      >
        <button
          type="button"
          disabled={page <= 1}
          onClick={() => onPageChange(page - 1)}
          className="h-8 text-xs px-3 py-2 rounded-lg  border border-line hover:bg-surface-hover dark:border-line-dark dark:hover:bg-surface-hover-dark
        disabled:opacity-40
    disabled:cursor-not-allowed
    disabled:hover:bg-transparent
    dark:disabled:hover:bg-transparent"
        >
          {t('pagination.previous')}
        </button>
        {Array.from({ length: totalPages }, (_, index) => index + 1).map((pageNumber) => (
          <button
            key={pageNumber}
            type="button"
            disabled={pageNumber === page}
            onClick={() => onPageChange(pageNumber)}
            aria-label={t('pagination.pageOf', { page: pageNumber, totalPages })}
            aria-current={pageNumber === page ? 'page' : undefined}
            className={`h-8  text-xs  min-w-10 shrink-0 rounded-lg border px-3 disabled:cursor-default disabled:opacity-100 ${
              pageNumber === page
                ? 'bg-fg text-white border-fg dark:bg-fg-dark dark:text-ink-on-dark dark:border-fg-dark'
              : 'border-line hover:bg-surface-hover dark:border-line-dark dark:hover:bg-surface-hover-dark'
            }`}
          >
            {pageNumber}
          </button>
        ))}
        <button
          type="button"
          disabled={page >= totalPages}
          onClick={() => onPageChange(page + 1)}
          className="h-8  text-xs px-3 py-2 rounded-lg  border border-line hover:bg-surface-hover dark:border-line-dark dark:hover:bg-surface-hover-dark
        disabled:opacity-40
    disabled:cursor-not-allowed
    disabled:hover:bg-transparent
    dark:disabled:hover:bg-transparent"
        >
          {t('pagination.next')}
        </button>
      </nav>
      <span className="shrink-0 text-xs text-fg-secondary dark:text-fg-secondary-dark">
        {totalItems === undefined
          ? pageLabel
          : t('pagination.totalRecords', { count: totalItems })}
      </span>
    </div>
  );
}