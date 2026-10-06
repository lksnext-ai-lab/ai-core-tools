import React, { type ReactNode } from 'react';
import { FileText } from 'lucide-react';

export interface TableColumn<T = any> {
  readonly header: string;
  readonly headerContent?: ReactNode;
  readonly accessor?: keyof T | ((row: T) => ReactNode);
  readonly className?: string;
  readonly headerClassName?: string;
  readonly render?: (row: T) => ReactNode;
}

export interface TableProps<T = any> {
  readonly columns: TableColumn<T>[];
  readonly data: T[];
  readonly keyExtractor: (row: T) => string | number;
  readonly emptyMessage?: string;
  readonly emptySubMessage?: string;
  readonly emptyIcon?: ReactNode;
  readonly loading?: boolean;
  readonly onRowClick?: (row: T) => void;
  readonly rowClassName?: string | ((row: T) => string);
  readonly className?: string;
}

function Table<T = any>({
  columns,
  data,
  keyExtractor,
  emptyMessage = 'No data found',
  emptySubMessage,
  emptyIcon = <FileText className="w-10 h-10 text-fg-faint2 dark:text-fg-faint2-dark" />,
  loading = false,
  onRowClick,
  rowClassName = 'hover:bg-surface-tint dark:hover:bg-surface-tint-dark',
  className = '',
}: TableProps<T>) {
  const getRowClassName = (row: T): string => {
    if (typeof rowClassName === 'function') {
      return rowClassName(row);
    }
    return rowClassName;
  };

  const getCellValue = (row: T, column: TableColumn<T>): ReactNode => {
    if (column.render) {
      return column.render(row);
    }
    
    if (typeof column.accessor === 'function') {
      return column.accessor(row);
    }
    
    if (column.accessor) {
      return row[column.accessor] as ReactNode;
    }
    
    return null;
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-accent dark:border-accent-dark"></div>
        <span className="ml-2 text-sm text-fg-tertiary dark:text-fg-tertiary-dark">Loading...</span>
      </div>
    );
  }

  return (
    <div className={`bg-surface border border-line rounded-lg overflow-visible dark:bg-surface-dark dark:border-line-dark ${className}`}>
      <div className="overflow-x-auto overflow-visible">
        <table className="min-w-full divide-y divide-line dark:divide-line-dark">
          <thead className="bg-tableCab dark:bg-tableCab-dark">
            <tr>
              {columns.map((column) => (
                <th
                  key={column.header}
                  className={
                    column.headerClassName ||
                    'px-6 py-3 text-left text-[11px] font-medium text-fg-tertiary uppercase tracking-[0.05em] dark:text-fg-tertiary-dark'
                  }
                >
                  {column.headerContent ?? column.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="bg-surface divide-y divide-line text-sm text-fg dark:bg-surface-dark dark:divide-line-dark dark:text-fg-dark">
            {data.length === 0 ? (
              <tr>
                <td colSpan={columns.length} className="px-6 py-8 text-center">
                  <div className="text-fg-tertiary dark:text-fg-tertiary-dark">
                    <div className="text-4xl mb-4 flex justify-center">{emptyIcon}</div>
                    <p className="font-display text-lg font-normal tracking-[-0.02em] text-fg dark:text-fg-dark">{emptyMessage}</p>
                    {emptySubMessage && (
                      <p className="text-sm mt-1">{emptySubMessage}</p>
                    )}
                  </div>
                </td>
              </tr>
            ) : (
              data.map((row) => (
                <tr
                  key={keyExtractor(row)}
                  className={getRowClassName(row)}
                  onClick={onRowClick ? () => onRowClick(row) : undefined}
                  style={onRowClick ? { cursor: 'pointer' } : undefined}
                >
                  {columns.map((column) => (
                    <td
                      key={column.header}
                      className={column.className || 'px-6 py-4 whitespace-nowrap'}
                    >
                      {getCellValue(row, column)}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default Table;
