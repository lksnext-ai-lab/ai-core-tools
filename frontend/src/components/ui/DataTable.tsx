import { useMemo, useState, type ReactNode } from 'react';
import { Search } from 'lucide-react';
import Table, { type TableColumn } from './Table';
import ActionDropdown, { type ActionItem } from './ActionDropdown';

export interface DataTableProps<T> {
  readonly title?: string;
  readonly subtitle?: string;
  readonly headerActions?: ReactNode;
  readonly searchable?: boolean;
  readonly searchPlaceholder?: string;
  readonly searchKeys?: ReadonlyArray<keyof T>;
  readonly data: ReadonlyArray<T>;
  readonly columns: ReadonlyArray<TableColumn<T>>;
  readonly keyExtractor: (row: T) => string | number;
  readonly rowActions?: (row: T) => ActionItem[];
  readonly loading?: boolean;
  readonly emptyMessage?: string;
  readonly emptySubMessage?: string;
  readonly emptyIcon?: ReactNode;
  readonly onRowClick?: (row: T) => void;
  readonly rowClassName?: string | ((row: T) => string);
  readonly className?: string;
}

function defaultMatch<T>(row: T, query: string, keys?: ReadonlyArray<keyof T>): boolean {
  const lowered = query.toLowerCase();
  const fields =
    keys && keys.length > 0
      ? keys
      : (Object.keys(row as Record<string, unknown>) as Array<keyof T>);
  return fields.some((key) => {
    const value = row[key];
    if (value == null) return false;
    return String(value).toLowerCase().includes(lowered);
  });
}

function DataTable<T>({
  title,
  subtitle,
  headerActions,
  searchable = false,
  searchPlaceholder = 'Search…',
  searchKeys,
  data,
  columns,
  keyExtractor,
  rowActions,
  loading = false,
  emptyMessage = 'No data found',
  emptySubMessage,
  emptyIcon,
  onRowClick,
  rowClassName,
  className = '',
}: DataTableProps<T>) {
  const [searchQuery, setSearchQuery] = useState('');

  const filteredData = useMemo<T[]>(() => {
    if (!searchable || !searchQuery.trim()) return [...data];
    return data.filter((row) => defaultMatch(row, searchQuery.trim(), searchKeys));
  }, [data, searchable, searchQuery, searchKeys]);

  const columnsWithActions = useMemo<TableColumn<T>[]>(() => {
    if (!rowActions) return [...columns];
    return [
      ...columns,
      {
        header: 'Actions',
        headerClassName:
          'px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider',
        className: 'px-6 py-4 whitespace-nowrap text-right',
        render: (row: T) => {
          const actions = rowActions(row);
          if (actions.length === 0) {
            return <span className="text-gray-400 text-sm">—</span>;
          }
          return (
            <div className="inline-flex justify-end">
              <ActionDropdown actions={actions} size="sm" />
            </div>
          );
        },
      },
    ];
  }, [columns, rowActions]);

  const showHeader = Boolean(title || subtitle || headerActions);

  return (
    <div className={`space-y-4 ${className}`}>
      {showHeader && (
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <div>
            {title && <h2 className="text-xl font-semibold text-gray-900">{title}</h2>}
            {subtitle && <p className="text-sm text-gray-600 mt-1">{subtitle}</p>}
          </div>
          {headerActions && <div className="flex items-center gap-2">{headerActions}</div>}
        </div>
      )}

      {searchable && (
        <div className="relative">
          <Search
            className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none"
            aria-hidden="true"
          />
          <input
            type="search"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder={searchPlaceholder}
            aria-label={searchPlaceholder}
            className="w-full sm:max-w-xs pl-9 pr-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
      )}

      <Table
        columns={columnsWithActions}
        data={filteredData}
        keyExtractor={keyExtractor}
        loading={loading}
        emptyMessage={emptyMessage}
        emptySubMessage={emptySubMessage}
        emptyIcon={emptyIcon}
        onRowClick={onRowClick}
        rowClassName={rowClassName}
      />
    </div>
  );
}

export default DataTable;
