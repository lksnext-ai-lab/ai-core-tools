import { useEffect, useState } from 'react';
import { Target, Trash2 } from 'lucide-react';
import type { MetadataOperator, SearchFilterMetadataField } from '../playground/SearchFilters';

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
        { _key: Math.random().toString(36).slice(2), field: fieldOptions[0] ?? '', op: '$eq', value: '' },
      ],
    });
  };

  const removeFilter = (index: number) => {
    onChange({ rag_fixed_filters: filters.filter((_, i) => i !== index) });
  };

  return (
    <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-8">
      <div className="flex items-center mb-6">
        <div className="w-10 h-10 bg-indigo-100 rounded-xl flex items-center justify-center mr-4">
          <Target className="w-5 h-5 text-indigo-600" aria-hidden="true" />
        </div>
        <div>
          <h3 className="text-xl font-semibold text-gray-900">Retrieval (RAG)</h3>
          <p className="text-sm text-gray-500">How this agent searches its knowledge base</p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div>
          <label htmlFor="rag_k" className="block text-sm font-medium text-gray-700 mb-2">
            Documents to retrieve (k)
          </label>
          <input
            id="rag_k"
            type="number"
            min={1}
            max={100}
            value={value.rag_k}
            onChange={(e) => onChange({ rag_k: clampInt(e.target.value, 1, 100, value.rag_k) })}
            className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all duration-200"
          />
          <p className="text-xs text-gray-500 mt-1">Number of chunks fetched per search (1–100).</p>
        </div>

        <div>
          <label htmlFor="rag_max_retrieval_calls" className="block text-sm font-medium text-gray-700 mb-2">
            Max retrieval calls per turn
          </label>
          <input
            id="rag_max_retrieval_calls"
            type="number"
            min={1}
            max={20}
            value={value.rag_max_retrieval_calls ?? ''}
            placeholder="Unlimited"
            onChange={(e) =>
              onChange({
                rag_max_retrieval_calls: e.target.value ? clampInt(e.target.value, 1, 20, 4) : null,
              })
            }
            className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all duration-200"
          />
          <p className="text-xs text-gray-500 mt-1">Caps how often the agent can search in one turn (1–20). Empty = unlimited.</p>
        </div>

        <div>
          <label htmlFor="rag_search_type" className="block text-sm font-medium text-gray-700 mb-2">
            Search strategy
          </label>
          <select
            id="rag_search_type"
            value={value.rag_search_type}
            onChange={(e) => onChange({ rag_search_type: e.target.value as RagSearchType })}
            className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all duration-200"
          >
            {SEARCH_TYPES.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </select>
        </div>

        {value.rag_search_type === 'similarity_score_threshold' && (
          <div>
            <label htmlFor="rag_score_threshold" className="block text-sm font-medium text-gray-700 mb-2">
              Score threshold
              <span className="text-red-500 ml-1" aria-hidden="true">*</span>
              <span className="sr-only"> (required)</span>
            </label>
            <input
              id="rag_score_threshold"
              type="text"
              inputMode="decimal"
              required
              value={thresholdText}
              placeholder="0.75"
              aria-invalid={thresholdMissing}
              aria-describedby="rag_score_threshold_help"
              onChange={(e) => handleThresholdChange(e.target.value)}
              onBlur={handleThresholdBlur}
              className={`w-full px-4 py-3 border rounded-xl focus:ring-2 transition-all duration-200 ${
                thresholdMissing
                  ? 'border-red-300 focus:ring-red-500 focus:border-red-500'
                  : 'border-gray-300 focus:ring-blue-500 focus:border-blue-500'
              }`}
            />
            {thresholdMissing ? (
              <p id="rag_score_threshold_help" role="alert" className="text-xs text-red-600 mt-1">
                Required for the threshold strategy (0–1).
              </p>
            ) : (
              <p id="rag_score_threshold_help" className="text-xs text-gray-500 mt-1">
                Minimum relevance score, 0–1. Lower returns more, higher is stricter.
              </p>
            )}
          </div>
        )}
      </div>

      {/* Fixed filters — always-applied scoping the caller cannot loosen */}
      <div className="mt-8">
        <div className="flex items-center justify-between mb-3">
          <div>
            <h4 className="text-sm font-semibold text-gray-900">Fixed metadata filters</h4>
            <p className="text-xs text-gray-500">Applied to every search. Leave empty to search the whole knowledge base.</p>
          </div>
          <button
            type="button"
            onClick={addFilter}
            disabled={filters.length >= MAX_FIXED_FILTERS}
            className="px-3 py-1.5 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-400 text-white text-sm rounded-lg transition-colors"
          >
            Add filter
          </button>
        </div>

        {loadingMetadata && <p className="text-sm text-gray-500">Loading metadata fields…</p>}

        {filters.length > 0 && (
          <div className="space-y-2">
            {filters.map((filter, index) => (
              <div key={filter._key ?? `${filter.field}-${index}`} className="grid grid-cols-12 gap-2 items-start">
                <select
                  aria-label={`Filter field, row ${index + 1}`}
                  value={filter.field}
                  onChange={(e) => updateFilter(index, { field: e.target.value })}
                  className="col-span-4 px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  {!fieldOptions.includes(filter.field) && filter.field && (
                    <option value={filter.field}>{filter.field}</option>
                  )}
                  {fieldOptions.map((name) => (
                    <option key={name} value={name}>
                      {name}
                    </option>
                  ))}
                </select>

                <select
                  aria-label={`Filter operator, row ${index + 1}`}
                  value={filter.op}
                  onChange={(e) => {
                    const op = e.target.value as MetadataOperator;
                    updateFilter(index, { op, value: inputToFilterValue(op, filterValueToInput(filter.value)) });
                  }}
                  className="col-span-3 px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  {OPERATORS.map((op) => (
                    <option key={op.value} value={op.value}>
                      {op.label}
                    </option>
                  ))}
                </select>

                <input
                  type="text"
                  aria-label={`Filter value, row ${index + 1}`}
                  value={filterValueToInput(filter.value)}
                  placeholder={filter.op === '$in' ? 'a, b, c' : 'value'}
                  onChange={(e) => updateFilter(index, { value: inputToFilterValue(filter.op, e.target.value) })}
                  className="col-span-4 px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
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
    </div>
  );
}

export default RagConfigSection;
