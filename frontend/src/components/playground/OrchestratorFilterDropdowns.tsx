import { useId, useState } from 'react';

export interface ChatFilterField {
  field_name: string;
  values: string[];
}

interface OrchestratorFilterDropdownsProps {
  readonly filters: ChatFilterField[];
  readonly selected: Record<string, string>;
  readonly onChange: (selected: Record<string, string>) => void;
  readonly disabled?: boolean;
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
  disabled = false,
}: Readonly<OrchestratorFilterDropdownsProps>) {
  const [isExpanded, setIsExpanded] = useState(false);
  const panelId = useId();

  if (filters.length === 0) {
    return null;
  }

  const activeEntries = Object.entries(selected).filter(([, value]) => value);
  const activeCount = activeEntries.length;

  const handleFieldChange = (fieldName: string, value: string) => {
    if (!value) {
      // Delete the key so a cleared field never sends an empty-string filter value.
      const { [fieldName]: _removed, ...rest } = selected;
      onChange(rest);
      return;
    }
    onChange({ ...selected, [fieldName]: value });
  };

  const handleClearOne = (fieldName: string) => handleFieldChange(fieldName, '');
  const handleClearAll = () => onChange({});

  return (
    <div className="pg-glass rounded-xl overflow-hidden">
      <button
        type="button"
        className="w-full px-4 py-3 flex items-center justify-between text-left hover:bg-white/30 dark:hover:bg-gray-700/30 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 transition-colors"
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
          {activeEntries.map(([fieldName, value]) => (
            <span
              key={fieldName}
              className="inline-flex items-center gap-1 pl-2.5 pr-1 py-1 rounded-full text-xs font-medium
                         bg-indigo-50 dark:bg-indigo-500/10 text-indigo-700 dark:text-indigo-300
                         border border-indigo-200 dark:border-indigo-500/30"
            >
              <span className="opacity-70">{humanizeFieldName(fieldName)}:</span>
              <span>{value}</span>
              <button
                type="button"
                onClick={() => handleClearOne(fieldName)}
                disabled={disabled}
                aria-label={`Clear ${humanizeFieldName(fieldName)} filter`}
                className="ml-0.5 rounded-full p-0.5 text-indigo-500 hover:text-indigo-700 hover:bg-indigo-100
                           dark:text-indigo-400 dark:hover:text-indigo-200 dark:hover:bg-indigo-500/20
                           disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </span>
          ))}
          {activeCount > 1 && (
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
        className={`border-t border-white/20 dark:border-gray-700/30 px-4 py-3 bg-white/20 dark:bg-gray-800/20 ${
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
              <select
                id={`${panelId}-${field.field_name}`}
                value={selected[field.field_name] ?? ''}
                onChange={(e) => handleFieldChange(field.field_name, e.target.value)}
                disabled={disabled}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg
                           bg-white dark:bg-gray-800 text-gray-800 dark:text-gray-100
                           focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent
                           disabled:opacity-50 disabled:cursor-not-allowed text-sm transition-shadow"
              >
                <option value="">— any —</option>
                {field.values.map((value) => (
                  <option key={value} value={value}>
                    {value}
                  </option>
                ))}
              </select>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export default OrchestratorFilterDropdowns;
