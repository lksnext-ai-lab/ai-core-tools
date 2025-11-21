import React, { type ReactNode } from 'react';

export interface TableColumn<T = any> {
  readonly header: string;
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
  readonly emptyIcon?: string;
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
  emptyIcon = '📄',
  loading = false,
  onRowClick,
  rowClassName = 'hover:bg-gray-50',
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
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
        <span className="ml-2">Loading...</span>
      </div>
    );
  }

  return (
    <div className={`bg-white shadow rounded-lg overflow-visible ${className}`}>
      <div className="overflow-x-auto overflow-visible">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              {columns.map((column) => (
                <th
                  key={column.header}
                  className={
                    column.headerClassName ||
                    'px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider'
                  }
                >
                  {column.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {data.length === 0 ? (
              <tr>
                <td colSpan={columns.length} className="px-6 py-8 text-center">
                  <div className="text-gray-500">
                    <div className="text-4xl mb-4">{emptyIcon}</div>
                    <p className="text-lg font-medium">{emptyMessage}</p>
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
