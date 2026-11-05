import { useId, useState } from 'react';
import SearchableMultiSelect from './SearchableMultiSelect';

export interface ChatFilterField {
  field_name: string;
  values: string[];
  /** True when `values` is only the first page and the rest must be searched on the backend. */
  has_more?: boolean;
}

export type ChatFilterSelection = Record<string, string[]>;

interface OrchestratorFilterDropdownsProps {
  readonly filters: ChatFilterField[];
  readonly selected: ChatFilterSelection;
  readonly onChange: (selected: ChatFilterSelection) => void;
  readonly onSearchValues?: (fieldName: string, query: string) => Promise<string[]>;
  readonly disabled?: boolean;
}

/**
 * Wire format for `search_params.filter`: one selected value is sent as a scalar
 * (`$eq`), several as a list (`$in`, "any of"); empty fields are dropped.
 */
export function toSearchFilter(
  selected: ChatFilterSelection,
): Record<string, string | string[]> | undefined {
  const entries = Object.entries(selected)
    .filter(([, values]) => values.length > 0)
    .map(([field, values]): [string, string | string[]] => [
      field,
      values.length === 1 ? values[0] : values,
    ]);
  return entries.length > 0 ? Object.fromEntries(entries) : undefined;
}

/** "modelo_maquina" -> "Modelo maquina" — developer-facing field names read as a label. */
function humanizeFieldName(fieldName: string): string {
  const spaced = fieldName.replace(/[_-]+/g, ' ').trim();
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

/**
 * Self-contained, collapsible panel for orchestrator-level metadata filters
 * (`Agent.exposed_chat_filters`) — aggregated across the orchestrator's own
 * silo + all its subagents' silos. The parent only owns fetching `filters`
 * and the `selected` state; presentation (collapse, chips, labels) lives here.
 */
function OrchestratorFilterDropdowns({
  filters,
  selected,
  onChange,
  onSearchValues,
  disabled = false,
}: Readonly<OrchestratorFilterDropdownsProps>) {
  const [isExpanded, setIsExpanded] = useState(false);
  const panelId = useId();

  if (filters.length === 0) {
    return null;
  }

  const activeEntries = Object.entries(selected).filter(([, values]) => values.length > 0);
  const activeCount = activeEntries.length;
  const totalSelectedValues = activeEntries.reduce((sum, [, values]) => sum + values.length, 0);

  const handleFieldChange = (fieldName: string, values: string[]) => {
    if (values.length === 0) {
      // Delete the key so a cleared field never sends an empty filter value.
      const { [fieldName]: _removed, ...rest } = selected;
      onChange(rest);
      return;
    }
    onChange({ ...selected, [fieldName]: values });
  };

  const handleRemoveValue = (fieldName: string, value: string) =>
    handleFieldChange(
      fieldName,
      (selected[fieldName] ?? []).filter((v) => v !== value),
    );
  const handleClearAll = () => onChange({});

  return (
    <div className="pg-glass rounded-xl">
      <button
        type="button"
        className={`w-full px-4 py-3 flex items-center justify-between text-left hover:bg-white/30 dark:hover:bg-gray-700/30 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 transition-colors ${
          isExpanded ? 'rounded-t-xl' : 'rounded-xl'
        }`}
        onClick={() => setIsExpanded((prev) => !prev)}
        aria-expanded={isExpanded}
        aria-controls={panelId}
      >
        <span className="flex items-center gap-2 text-sm font-medium text-gray-700 dark:text-gray-300">
          <svg
            className="w-4 h-4 text-indigo-500"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
            aria-hidden="true"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M6 12h12M3 6h18M9 18h6"
            />
          </svg>
          Filters
          {activeCount > 0 && (
            <span className="inline-flex items-center justify-center min-w-[1.25rem] h-5 px-1.5 rounded-full bg-indigo-500 text-white text-xs font-semibold">
              {activeCount}
            </span>
          )}
        </span>
        <svg
          className={`w-4 h-4 text-gray-400 transition-transform duration-200 ${
            isExpanded ? 'rotate-180' : ''
          }`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
          aria-hidden="true"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {/* Active-filter chips stay visible even while collapsed — the conversation
          is actually being scoped by these, so hiding them would be misleading. */}
      {activeCount > 0 && (
        <div className="flex items-center gap-1.5 flex-wrap px-4 pb-3 pt-0.5">
          {activeEntries.map(([fieldName, values]) =>
            values.map((value) => (
              <span
                key={`${fieldName}\u0000${value}`}
                className="inline-flex items-center gap-1 pl-2.5 pr-1 py-1 rounded-full text-xs font-medium
                           bg-indigo-50 dark:bg-indigo-500/10 text-indigo-700 dark:text-indigo-300
                           border border-indigo-200 dark:border-indigo-500/30"
              >
                <span className="opacity-70">{humanizeFieldName(fieldName)}:</span>
                <span>{value}</span>
                <button
                  type="button"
                  onClick={() => handleRemoveValue(fieldName, value)}
                  disabled={disabled}
                  aria-label={`Remove ${value} from ${humanizeFieldName(fieldName)} filter`}
                  className="ml-0.5 rounded-full p-0.5 text-indigo-500 hover:text-indigo-700 hover:bg-indigo-100
                             dark:text-indigo-400 dark:hover:text-indigo-200 dark:hover:bg-indigo-500/20
                             disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </span>
            )),
          )}
          {totalSelectedValues > 1 && (
            <button
              type="button"
              onClick={handleClearAll}
              disabled={disabled}
              className="text-xs font-medium text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200
                         underline-offset-2 hover:underline disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              Clear all
            </button>
          )}
        </div>
      )}

      <div
        id={panelId}
        className={`border-t border-white/20 dark:border-gray-700/30 px-4 py-3 bg-white/20 dark:bg-gray-800/20 rounded-b-xl ${
          isExpanded ? '' : 'hidden'
        }`}
      >
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filters.map((field) => (
            <div key={field.field_name}>
              <label
                htmlFor={`${panelId}-${field.field_name}`}
                className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1"
              >
                {humanizeFieldName(field.field_name)}
              </label>
              <SearchableMultiSelect
                id={`${panelId}-${field.field_name}`}
                value={selected[field.field_name] ?? []}
                options={field.values}
                onSearch={
                  field.has_more && onSearchValues
                    ? (query) => onSearchValues(field.field_name, query)
                    : undefined
                }
                onChange={(values) => handleFieldChange(field.field_name, values)}
                disabled={disabled}
              />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export default OrchestratorFilterDropdowns;
