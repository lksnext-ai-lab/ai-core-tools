import { useEffect, useState } from 'react';
import { Target, Trash2 } from 'lucide-react';
import type { MetadataOperator, SearchFilterMetadataField } from '../playground/SearchFilters';
import { randomId } from '../../utils/randomId';
import BackgroundImage from '../ui/BackgroundImage';
import CardApp from '../ui/CardApp';
import FormField, { FormSelect } from '../ui/FormField';
import ButtonApp from '../ui/ButtonApp';

export type RagSearchType = 'similarity' | 'mmr' | 'similarity_score_threshold';

export interface RagFixedFilter {
  field: string;
  op: MetadataOperator;
  value: unknown;
  _key?: string;
}

export interface RagConfigValue {
  rag_k: number;
  rag_search_type: RagSearchType;
  rag_score_threshold: number | null;
  rag_max_retrieval_calls: number | null;
  rag_fixed_filters: RagFixedFilter[];
}

interface RagConfigSectionProps {
  value: RagConfigValue;
  onChange: (patch: Partial<RagConfigValue>) => void;
  metadataFields: SearchFilterMetadataField[];
  loadingMetadata?: boolean;
}

// Mirrors backend SYSTEM_METADATA_FIELDS — always filterable regardless of metadata_definition.
const SYSTEM_FIELDS = ['name', 'file_type', 'url', 'page'];

const SEARCH_TYPES: Array<{ value: RagSearchType; label: string }> = [
  { value: 'similarity', label: 'Similarity (default)' },
  { value: 'mmr', label: 'MMR — diverse results' },
  { value: 'similarity_score_threshold', label: 'Similarity + score threshold' },
];

const OPERATORS: Array<{ value: MetadataOperator; label: string }> = [
  { value: '$eq', label: 'equals' },
  { value: '$ne', label: 'not equals' },
  { value: '$gt', label: 'greater than' },
  { value: '$gte', label: 'greater or equal' },
  { value: '$lt', label: 'less than' },
  { value: '$lte', label: 'less or equal' },
  { value: '$in', label: 'in (comma-separated)' },
];

const MAX_FIXED_FILTERS = 10;

// Shared between the inline field error and the form-level submit guard.
export const SCORE_THRESHOLD_REQUIRED_MSG =
  'A score threshold (0–1) is required for the "Similarity + score threshold" strategy.';

function clampInt(raw: string, min: number, max: number, fallback: number): number {
  const n = Number.parseInt(raw, 10);
  if (Number.isNaN(n)) return fallback;
  return Math.min(max, Math.max(min, n));
}

/** Render a stored filter value for editing: $in arrays become a comma-separated string. */
function filterValueToInput(value: unknown): string {
  if (Array.isArray(value)) return value.join(', ');
  if (value === null || value === undefined) return '';
  return String(value);
}

/** Convert the edited string back to the stored shape ($in → list, others → scalar string). */
function inputToFilterValue(op: MetadataOperator, raw: string): unknown {
  if (op === '$in') {
    return raw.split(',').map((v) => v.trim()).filter(Boolean);
  }
  return raw;
}

/**
 * Per-agent RAG retrieval configuration. Only meaningful when the agent has a silo;
 * the caller renders this conditionally. Values are persisted on the Agent and resolved
 * at execution time (caller > agent > system).
 */
function RagConfigSection({ value, onChange, metadataFields, loadingMetadata = false }: Readonly<RagConfigSectionProps>) {
  const fieldOptions = [...SYSTEM_FIELDS, ...metadataFields.map((f) => f.name)];
  const filters = value.rag_fixed_filters;
  const thresholdMissing =
    value.rag_search_type === 'similarity_score_threshold' && value.rag_score_threshold == null;

  // Local text buffer for the decimal threshold: lets the user type "0,6"/"0." freely
  // (comma normalized to dot) without the controlled-number-input swallowing keystrokes.
  const [thresholdText, setThresholdText] = useState(
    value.rag_score_threshold == null ? '' : String(value.rag_score_threshold),
  );

  // Re-sync the buffer when the value changes from outside (agent load, strategy switch).
  useEffect(() => {
    const parsed = thresholdText.trim() === '' ? null : Number.parseFloat(thresholdText.replace(',', '.'));
    const normalized = Number.isFinite(parsed as number) ? parsed : null;
    if ((value.rag_score_threshold ?? null) !== normalized) {
      setThresholdText(value.rag_score_threshold == null ? '' : String(value.rag_score_threshold));
    }
  }, [value.rag_score_threshold]);

  const handleThresholdChange = (raw: string) => {
    setThresholdText(raw);
    const n = Number.parseFloat(raw.replace(',', '.'));
    onChange({ rag_score_threshold: Number.isFinite(n) ? n : null });
  };

  const handleThresholdBlur = () => {
    if (value.rag_score_threshold == null) return;
    const clamped = Math.min(1, Math.max(0, value.rag_score_threshold));
    if (clamped !== value.rag_score_threshold) onChange({ rag_score_threshold: clamped });
    setThresholdText(String(clamped));
  };

  const updateFilter = (index: number, patch: Partial<RagFixedFilter>) => {
    onChange({
      rag_fixed_filters: filters.map((f, i) => (i === index ? { ...f, ...patch } : f)),
    });
  };

  const addFilter = () => {
    if (filters.length >= MAX_FIXED_FILTERS) return;
    onChange({
      rag_fixed_filters: [
        ...filters,
        { _key: randomId(), field: fieldOptions[0] ?? '', op: '$eq', value: '' },
      ],
    });
  };

  const removeFilter = (index: number) => {
    onChange({ rag_fixed_filters: filters.filter((_, i) => i !== index) });
  };

  return (
    <CardApp className=" p-8">
      <div className="flex items-center mb-6">
        <BackgroundImage icon={Target} iconSize={20} size={40} className='mr-2' />  
        <div>
          <h3 className="text-lg font-semibold text-fg dark:text-fg-dark">Retrieval (RAG)</h3>
          <p className="text-sm text-fg-secondary dark:text-fg-secondary-dark">How this agent searches its knowledge base</p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div>
          <FormField
            label="Documents to retrieve (k)"
            id="rag_k"
            type="number"
            min={1}
            max={100}
            value={value.rag_k}
            helpText="Number of chunks fetched per search (1–100)."
            onChange={(e) => onChange({ rag_k: clampInt(e.target.value, 1, 100, value.rag_k) })}
          />
        </div>

        <div>
          <FormField
            label="Max retrieval calls per turn"
            id="rag_max_retrieval_calls"
            type="number"
            min={1}
            max={20}
            value={value.rag_max_retrieval_calls ?? ''}
            placeholder="Unlimited"
            helpText="Caps how often the agent can search in one turn (1–20). Empty = unlimited."
            onChange={(e) =>
              onChange({
                rag_max_retrieval_calls: e.target.value ? clampInt(e.target.value, 1, 20, 4) : null,
              })
            }
          />
        </div>

        <FormSelect
          label="Search strategy"
            id="rag_search_type"
            value={value.rag_search_type}
          options={SEARCH_TYPES}
            onChange={(e) => onChange({ rag_search_type: e.target.value as RagSearchType })}
        />

        {value.rag_search_type === 'similarity_score_threshold' && (
          <div>
            <FormField
              label="Score threshold"
              id="rag_score_threshold"
              type="text"
              inputMode="decimal"
              required
              value={thresholdText}
              placeholder="0.75"
              error={thresholdMissing ? 'Required for the threshold strategy (0–1).' : undefined}
              helpText={thresholdMissing ? undefined : 'Minimum relevance score, 0–1. Lower returns more, higher is stricter.'}
              onChange={(e) => handleThresholdChange(e.target.value)}
              onBlur={handleThresholdBlur}
            />
          </div>
        )}
      </div>

      {/* Fixed filters — always-applied scoping the caller cannot loosen */}
      <div className="mt-8">
        <div className="flex items-center justify-between mb-3">
          <div>
            <h4 className="text-sm font-semibold text-fg dark:text-fg-dark">Fixed metadata filters</h4>
            <p className="text-xs text-fg-secondary dark:text-fg-secondary-dark">Applied to every search. Leave empty to search the whole knowledge base.</p>
          </div>
          <ButtonApp
            label="Add filter"
            type="button"
            onClick={addFilter}
            disabled={filters.length >= MAX_FIXED_FILTERS}
            variant="primary"
            size="medium"
          />
        </div>

        {loadingMetadata && <p className="text-sm text-gray-500">Loading metadata fields…</p>}

        {filters.length > 0 && (
          <div className="space-y-2">
            {filters.map((filter, index) => (
              <div key={filter._key ?? `${filter.field}-${index}`} className="grid grid-cols-12 gap-2 items-start">
                <FormSelect
                  id={`rag-filter-field-${index}`}
                  label={`Filter field, row ${index + 1}`}
                  labelClassName="sr-only"
                  value={filter.field}
                  className="col-span-4"
                  options={[
                    ...(!fieldOptions.includes(filter.field) && filter.field
                      ? [{ value: filter.field, label: filter.field }]
                      : []),
                    ...fieldOptions.map((name) => ({ value: name, label: name })),
                  ]}
                  onChange={(e) => updateFilter(index, { field: e.target.value })}
                />

                <FormSelect
                  id={`rag-filter-operator-${index}`}
                  label={`Filter operator, row ${index + 1}`}
                  labelClassName="sr-only"
                  value={filter.op}
                  className="col-span-3"
                  options={OPERATORS}
                  onChange={(e) => {
                    const op = e.target.value as MetadataOperator;
                    updateFilter(index, { op, value: inputToFilterValue(op, filterValueToInput(filter.value)) });
                  }}
                />

                <FormField
                  id={`rag-filter-value-${index}`}
                  type="text"
                  ariaLabel={`Filter value, row ${index + 1}`}
                  value={filterValueToInput(filter.value)}
                  placeholder={filter.op === '$in' ? 'a, b, c' : 'value'}
                  className="col-span-4"
                  inputClassName="text-sm"
                  onChange={(e) => updateFilter(index, { value: inputToFilterValue(filter.op, e.target.value) })}
                />

                <button
                  type="button"
                  onClick={() => removeFilter(index)}
                  title="Remove filter"
                  aria-label={`Remove filter, row ${index + 1}`}
                  className="col-span-1 flex justify-center text-red-600 hover:text-red-800 transition-colors p-2 rounded focus:outline-none focus:ring-2 focus:ring-red-500"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </CardApp>
  );
}

export default RagConfigSection;
