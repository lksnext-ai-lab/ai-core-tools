/** Page navigator shared by the marketplace catalogs. */
interface PaginationProps {
  readonly page: number;
  readonly totalPages: number;
  readonly onPageChange: (page: number) => void;
}

export function Pagination({ page, totalPages, onPageChange }: PaginationProps) {
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
