import { useId, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ChevronDown, SlidersHorizontal, X } from 'lucide-react';
import SearchableMultiSelect from './SearchableMultiSelect';
import { Badge } from '../ui/Badge';

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
  const { t } = useTranslation('common');
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
    <div className="rounded-md border border-line bg-surface dark:border-btCard-border-dark dark:bg-surface-dark">
      <button
        type="button"
        className={`flex w-full items-center justify-between px-4 py-3 text-left transition-colors hover:bg-surface-hover focus:outline-none focus-visible:ring-2 focus-visible:ring-focus dark:hover:bg-surface-hover-dark dark:focus-visible:ring-focus-dark ${
          isExpanded ? 'rounded-t-md' : 'rounded-md'
        }`}
        onClick={() => setIsExpanded((prev) => !prev)}
        aria-expanded={isExpanded}
        aria-controls={panelId}
      >
        <span className="flex items-center gap-2 text-sm font-medium text-fg dark:text-fg-dark">
          <SlidersHorizontal className="h-4 w-4 text-fg-secondary dark:text-fg-secondary-dark" aria-hidden="true" />
          {t('orchestratorFilters.title')}
          {activeCount > 0 && <Badge variant="primary" label={String(activeCount)} />}
        </span>
        <ChevronDown
          className={`h-4 w-4 text-fg-tertiary transition-transform dark:text-fg-tertiary-dark ${
            isExpanded ? 'rotate-180' : ''
          }`}
          aria-hidden="true"
        />
      </button>

      {/* Active-filter chips stay visible even while collapsed — the conversation
          is actually being scoped by these, so hiding them would be misleading. */}
      {activeCount > 0 && (
        <div className="flex items-center gap-1.5 flex-wrap px-4 pb-3 pt-0.5">
          {activeEntries.map(([fieldName, values]) =>
            values.map((value) => (
              <span
                key={`${fieldName}\u0000${value}`}
                className="inline-flex items-center gap-1 rounded-full bg-bronze-bg-soft py-1 pl-2.5 pr-1 text-xs font-medium
                           text-bronze-strong dark:bg-bronze-bg-soft-dark dark:text-bronze-strong-dark"
              >
                <span className="opacity-70">{humanizeFieldName(fieldName)}:</span>
                <span>{value}</span>
                <button
                  type="button"
                  onClick={() => handleRemoveValue(fieldName, value)}
                  disabled={disabled}
                  aria-label={t('orchestratorFilters.removeValue', { value, field: humanizeFieldName(fieldName) })}
                  className="ml-0.5 rounded-full p-0.5 transition-colors hover:bg-surface-hover focus:outline-none
                             focus-visible:ring-2 focus-visible:ring-focus dark:hover:bg-surface-hover-dark
                             dark:focus-visible:ring-focus-dark disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <X className="h-3 w-3" aria-hidden="true" />
                </button>
              </span>
            )),
          )}
          {totalSelectedValues > 1 && (
            <button
              type="button"
              onClick={handleClearAll}
              disabled={disabled}
              className="text-xs font-medium text-fg-secondary underline-offset-2 transition-colors hover:text-fg hover:underline
                         disabled:cursor-not-allowed disabled:opacity-50 dark:text-fg-secondary-dark dark:hover:text-fg-dark"
            >
              {t('orchestratorFilters.clearAll')}
            </button>
          )}
        </div>
      )}

      <div
        id={panelId}
        className={`border-t border-line px-4 py-3 dark:border-line-dark ${isExpanded ? '' : 'hidden'}`}
      >
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filters.map((field) => (
            <div key={field.field_name}>
              <label
                htmlFor={`${panelId}-${field.field_name}`}
                className="mb-1 block text-sm font-medium text-fg dark:text-fg-dark"
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
