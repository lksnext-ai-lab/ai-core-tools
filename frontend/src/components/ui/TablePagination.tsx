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

  const pageLabel = totalItems === undefined
    ? t('pagination.pageOf', { page, totalPages })
    : t('pagination.pageOfWithTotal', { page, totalPages, total: totalItems });

  return (
    <nav className="mt-4 flex items-center justify-center gap-1" aria-label={t('pagination.ariaLabel')}>
      <button
        type="button"
        disabled={page <= 1}
        onClick={() => onPageChange(page - 1)}
        className="rounded-lg border border-gray-300 px-3 py-2 text-sm hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-40"
      >
        {t('pagination.previous')}
      </button>
      <span className="px-2 text-sm text-gray-600">{pageLabel}</span>
      <button
        type="button"
        disabled={page >= totalPages}
        onClick={() => onPageChange(page + 1)}
        className="rounded-lg border border-gray-300 px-3 py-2 text-sm hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-40"
      >
        {t('pagination.next')}
      </button>
    </nav>
  );
}