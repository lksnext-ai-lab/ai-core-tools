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

/**
 * Presentational-only dropdown row for orchestrator-level metadata filters
 * (`Agent.exposed_chat_filters`). One native `<select>` per field, aggregated
 * across the orchestrator's own silo + all its subagents' silos. The parent
 * owns fetching `filters` and the `selected` state — this component never
 * calls the API itself.
 */
function OrchestratorFilterDropdowns({
  filters,
  selected,
  onChange,
  disabled = false,
}: Readonly<OrchestratorFilterDropdownsProps>) {
  if (filters.length === 0) {
    return null;
  }

  const handleFieldChange = (fieldName: string, value: string) => {
    if (!value) {
      // Actually delete the key so a cleared field never sends an empty-string filter value.
      const { [fieldName]: _removed, ...rest } = selected;
      onChange(rest);
      return;
    }
    onChange({ ...selected, [fieldName]: value });
  };

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      {filters.map((field) => (
        <div key={field.field_name}>
          <label
            htmlFor={`orchestrator-filter-${field.field_name}`}
            className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1"
          >
            {field.field_name}
          </label>
          <select
            id={`orchestrator-filter-${field.field_name}`}
            value={selected[field.field_name] ?? ''}
            onChange={(e) => handleFieldChange(field.field_name, e.target.value)}
            disabled={disabled}
            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg
                       bg-white dark:bg-gray-800 text-gray-800 dark:text-gray-100
                       focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent
                       disabled:opacity-50 disabled:cursor-not-allowed text-sm"
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
  );
}

export default OrchestratorFilterDropdowns;
