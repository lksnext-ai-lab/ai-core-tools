import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { apiService } from '../../services/api';
import ButtonApp from '../ui/ButtonApp';
import { FormField, FormSelect } from '../ui/FormField';

export type MetadataOperator = '$eq' | '$ne' | '$gt' | '$gte' | '$lt' | '$lte' | '$in';
export type SupportedDbType = 'PGVECTOR' | 'QDRANT';

export interface SearchFilterMetadataField {
  name: string;
  type: string;
  description?: string;
}

interface PreparedFilter {
  fieldName: string;
  operator: MetadataOperator;
  nativeOperator: string;
  value: unknown;
}

interface SavedFilter {
  id: number;
  name: string;
  filter: Record<string, unknown>;
}

interface SearchFiltersProps {
  metadataFields?: SearchFilterMetadataField[];
  dbType?: string;
  disabled?: boolean;
  onFilterMetadataChange: (filterMetadata: Record<string, unknown> | undefined) => void;
  appId?: string | number;
  siloId?: string | number;
  siloStorageKey?: string;
  /** `inline` (default): label, operator and value on one row.
   *  `stacked`: label above, operator + value below — for narrow side columns. */
  layout?: 'inline' | 'stacked';
}

const DEFAULT_DB_TYPE: SupportedDbType = 'PGVECTOR';
const QDRANT_METADATA_PREFIX = 'metadata.';

const FILTER_OPERATOR_MAPPINGS: Record<SupportedDbType, Record<MetadataOperator, string>> = {
  PGVECTOR: {
    $eq: '$eq',
    $ne: '$ne',
    $gt: '$gt',
    $gte: '$gte',
    $lt: '$lt',
    $lte: '$lte',
    $in: '$in',
  },
  QDRANT: {
    $eq: 'match',
    $ne: 'must_not_match',
    $gt: 'gt',
    $gte: 'gte',
    $lt: 'lt',
    $lte: 'lte',
    $in: 'match_any',
  },
};

const OPERATOR_TRANSLATION_KEYS: Record<MetadataOperator, string> = {
  $eq: 'equals',
  $ne: 'notEquals',
  $gt: 'greaterThan',
  $gte: 'greaterThanOrEqual',
  $lt: 'lessThan',
  $lte: 'lessThanOrEqual',
  $in: 'inAnyOf',
};

function normalizeDbType(dbType?: string): SupportedDbType {
  if (dbType?.toUpperCase() === 'QDRANT') {
    return 'QDRANT';
  }
  return DEFAULT_DB_TYPE;
}

function isStringType(fieldType: string): boolean {
  return ['string', 'str', 'keyword', 'text'].includes(fieldType.toLowerCase());
}

function isNumericType(fieldType: string): boolean {
  return ['int', 'float', 'number'].includes(fieldType.toLowerCase());
}

function isBoolType(fieldType: string): boolean {
  return fieldType.toLowerCase() === 'bool';
}

function getOperatorsForType(fieldType: string): MetadataOperator[] {
  if (isNumericType(fieldType)) {
    return ['$eq', '$ne', '$gt', '$gte', '$lt', '$lte'];
  }
  if (isBoolType(fieldType)) {
    return ['$eq', '$ne'];
  }
  // string, str, keyword, text, or unknown
  return ['$eq', '$ne', '$in'];
}

function buildPgvectorFilter(filters: PreparedFilter[], logicalOperator: '$and' | '$or') {
  if (filters.length === 0) {
    return undefined;
  }

  if (filters.length === 1) {
    const { fieldName, nativeOperator, value } = filters[0];
    return { [fieldName]: { [nativeOperator]: value } };
  }

  const conditions = filters.map(({ fieldName, nativeOperator, value }) => ({
    [fieldName]: { [nativeOperator]: value },
  }));

  return { [logicalOperator]: conditions };
}

function buildQdrantFilter(filters: PreparedFilter[], logicalOperator: '$and' | '$or') {
  if (filters.length === 0) {
    return undefined;
  }

  const must: Array<Record<string, unknown>> = [];
  const should: Array<Record<string, unknown>> = [];
  const mustNot: Array<Record<string, unknown>> = [];
  const targetList = logicalOperator === '$and' ? must : should;

  filters.forEach(({ fieldName, nativeOperator, value }) => {
    const key = `${QDRANT_METADATA_PREFIX}${fieldName}`;

    switch (nativeOperator) {
      case 'must_not_match':
        mustNot.push({ key, match: { value } });
        break;
      case 'match':
        targetList.push({ key, match: { value } });
        break;
      case 'match_any':
        targetList.push({ key, match: { any: value } });
        break;
      case 'gt':
      case 'gte':
      case 'lt':
      case 'lte':
        targetList.push({ key, range: { [nativeOperator]: value } });
        break;
      default:
        targetList.push({ key, match: { value } });
    }
  });

  const qdrantFilter: Record<string, unknown> = {};
  if (must.length > 0) qdrantFilter.must = must;
  if (should.length > 0) qdrantFilter.should = should;
  if (mustNot.length > 0) qdrantFilter.must_not = mustNot;

  return Object.keys(qdrantFilter).length > 0 ? qdrantFilter : undefined;
}

function convertMetadataValue(fieldType: string, rawValue: string): unknown {
  switch (fieldType) {
    case 'int': {
      const parsed = Number.parseInt(rawValue, 10);
      return Number.isNaN(parsed) ? rawValue : parsed;
    }
    case 'float': {
      const parsed = Number.parseFloat(rawValue);
      return Number.isNaN(parsed) ? rawValue : parsed;
    }
    case 'bool':
      return rawValue.trim().toLowerCase() === 'true';
    default:
      return rawValue;
  }
}

function prepareFilters(
  metadataFilters: Record<string, string>,
  filterOperators: Record<string, MetadataOperator>,
  metadataFields: SearchFilterMetadataField[] | undefined,
  operatorMapping: Record<MetadataOperator, string>,
): PreparedFilter[] {
  const prepared: PreparedFilter[] = [];

  Object.entries(metadataFilters).forEach(([fieldName, rawValue]) => {
    const trimmedValue = rawValue.trim();
    if (!trimmedValue) return;

    const selectedOperator = filterOperators[fieldName] || '$eq';
    const nativeOperator = operatorMapping[selectedOperator];
    if (!nativeOperator) return;

    const fieldDefinition = metadataFields?.find((field) => field.name === fieldName);
    let convertedValue: unknown;

    if (selectedOperator === '$in') {
      convertedValue = trimmedValue.split(',').map((v) => v.trim()).filter(Boolean);
    } else {
      convertedValue = fieldDefinition
        ? convertMetadataValue(fieldDefinition.type, trimmedValue)
        : trimmedValue;
    }

    prepared.push({ fieldName, operator: selectedOperator, nativeOperator, value: convertedValue });
  });

  return prepared;
}

function loadSavedFilters(key: string): SavedFilter[] {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as SavedFilter[]) : [];
  } catch {
    return [];
  }
}

export function SearchFilters({
  metadataFields,
  dbType,
  disabled = false,
  onFilterMetadataChange,
  appId,
  siloId,
  siloStorageKey,
  layout = 'inline',
}: Readonly<SearchFiltersProps>) {
  const { t } = useTranslation('common');
  const isStacked = layout === 'stacked';
  const [metadataFilters, setMetadataFilters] = useState<Record<string, string>>({});
  const [filterOperators, setFilterOperators] = useState<Record<string, MetadataOperator>>({});
  const [logicalOperator, setLogicalOperator] = useState<'$and' | '$or'>('$and');

  // Autocomplete
  const [suggestions, setSuggestions] = useState<Record<string, string[]>>({});
  const [openSuggestionField, setOpenSuggestionField] = useState<string | null>(null);
  const debounceTimers = useRef<Record<string, ReturnType<typeof setTimeout>>>({});

  // Saved filters
  const storageKey = useMemo(
    () => `silo-saved-filters-${siloStorageKey ?? 'global'}`,
    [siloStorageKey],
  );
  const [savedFilters, setSavedFilters] = useState<SavedFilter[]>(() => loadSavedFilters(storageKey));
  const [showSaveForm, setShowSaveForm] = useState(false);
  const [saveFilterName, setSaveFilterName] = useState('');
  const [loadSelectValue, setLoadSelectValue] = useState('');
  const [loadedFilterName, setLoadedFilterName] = useState<string | null>(null);

  // Reload saved filters when storage key changes (different silo)
  useEffect(() => {
    setSavedFilters(loadSavedFilters(storageKey));
    setLoadedFilterName(null);
    setLoadSelectValue('');
  }, [storageKey]);

  useEffect(() => {
    setMetadataFilters({});
    setFilterOperators({});
    setLogicalOperator('$and');
    setLoadedFilterName(null);
  }, [metadataFields]);

  useEffect(() => {
    if (!metadataFields || metadataFields.length === 0) {
      onFilterMetadataChange(undefined);
    }
  }, [metadataFields, onFilterMetadataChange]);

  const normalizedDbType = useMemo(() => normalizeDbType(dbType), [dbType]);
  const operatorMapping = FILTER_OPERATOR_MAPPINGS[normalizedDbType];

  const filterMetadata = useMemo(() => {
    const prepared = prepareFilters(metadataFilters, filterOperators, metadataFields, operatorMapping);
    return normalizedDbType === 'QDRANT'
      ? buildQdrantFilter(prepared, logicalOperator)
      : buildPgvectorFilter(prepared, logicalOperator);
  }, [metadataFilters, filterOperators, logicalOperator, metadataFields, normalizedDbType, operatorMapping]);

  useEffect(() => {
    onFilterMetadataChange(filterMetadata);
  }, [filterMetadata, onFilterMetadataChange]);

  // Autocomplete fetch
  const fetchSuggestions = useCallback(
    (fieldName: string, prefix: string) => {
      if (!appId || !siloId || prefix.length < 1) {
        setSuggestions((prev) => ({ ...prev, [fieldName]: [] }));
        return;
      }
      void apiService
        .getSiloMetadataValues(appId, siloId, fieldName, prefix, 10)
        .then((res) => {
          const values = (res as { values?: string[] }).values ?? [];
          setSuggestions((prev) => ({ ...prev, [fieldName]: values }));
          if (values.length > 0) setOpenSuggestionField(fieldName);
        })
        .catch(() => {
          setSuggestions((prev) => ({ ...prev, [fieldName]: [] }));
        });
    },
    [appId, siloId],
  );

  const handleMetadataFilterChange = (fieldName: string, value: string, operator: MetadataOperator) => {
    setMetadataFilters((prev) => ({ ...prev, [fieldName]: value }));
    setFilterOperators((prev) => ({ ...prev, [fieldName]: operator }));
  };

  const handleStringInputChange = (field: SearchFilterMetadataField, value: string, operator: MetadataOperator) => {
    handleMetadataFilterChange(field.name, value, operator);
    if (operator === '$in') return; // comma-separated — skip autocomplete

    if (debounceTimers.current[field.name]) clearTimeout(debounceTimers.current[field.name]);
    debounceTimers.current[field.name] = setTimeout(() => fetchSuggestions(field.name, value), 250);
  };

  const handleSuggestionClick = (fieldName: string, suggestion: string) => {
    handleMetadataFilterChange(fieldName, suggestion, filterOperators[fieldName] || '$eq');
    setSuggestions((prev) => ({ ...prev, [fieldName]: [] }));
    setOpenSuggestionField(null);
  };

  const handleInputBlur = (fieldName: string) => {
    setTimeout(() => {
      setOpenSuggestionField((prev) => (prev === fieldName ? null : prev));
    }, 150);
  };

  const handleInputKeyDown = (_fieldName: string, e: React.KeyboardEvent) => {
    if (e.key === 'Escape') setOpenSuggestionField(null);
  };

  // Saved filters helpers
  const persistSavedFilters = (filters: SavedFilter[]) => {
    setSavedFilters(filters);
    try {
      localStorage.setItem(storageKey, JSON.stringify(filters));
    } catch {
      // ignore storage errors
    }
  };

  const handleSaveFilter = () => {
    const name = saveFilterName.trim();
    if (!name || !filterMetadata) return;
    persistSavedFilters([...savedFilters, { id: Date.now(), name, filter: filterMetadata }]);
    setSaveFilterName('');
    setShowSaveForm(false);
  };

  const handleLoadFilter = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const id = Number(e.target.value);
    if (!id) return;
    const found = savedFilters.find((f) => f.id === id);
    if (found) {
      onFilterMetadataChange(found.filter);
      setLoadedFilterName(found.name);
    }
    setLoadSelectValue('');
  };

  const handleRemoveLoadedFilter = () => {
    if (!loadedFilterName) return;
    const found = savedFilters.find((f) => f.name === loadedFilterName);
    if (found) persistSavedFilters(savedFilters.filter((f) => f.id !== found.id));
    onFilterMetadataChange(undefined);
    setLoadedFilterName(null);
  };

  if (!metadataFields || metadataFields.length === 0) {
    return null;
  }

  return (
    <div>
      <div className={isStacked ? 'mb-3.5' : 'mb-3 flex items-center justify-end'}>
        <div className={isStacked ? '' : 'flex items-center gap-2'}>
          <FormSelect
            label={t('searchFilters.match')}
            labelClassName={isStacked
              ? 'text-[12.5px] font-medium text-fg dark:text-fg-dark mb-0 whitespace-nowrap'
              : 'text-[13px] text-fg-secondary dark:text-fg-secondary-dark mb-0 whitespace-nowrap'}
            selectClassName={isStacked ? '!py-1.5 !text-[13px] min-w-0 flex-1' : '!py-1.5 !text-[13px]'}
            id="logicalOperator"
            value={logicalOperator}
            onChange={(e) => setLogicalOperator(e.target.value as '$and' | '$or')}
            disabled={disabled}
            options={[
              { value: '$and', label: t('searchFilters.allFilters') },
              { value: '$or', label: t('searchFilters.anyFilter') },
            ]}
            className="flex items-center gap-2"
          />
        </div>
      </div>

      <div className={isStacked ? 'flex flex-col gap-3' : 'flex flex-col gap-2.5'}>
        {metadataFields.map((field) => {
          const allowedOps = getOperatorsForType(field.type);
          const rawOp = filterOperators[field.name] || '$eq';
          const currentOp = allowedOps.includes(rawOp) ? rawOp : allowedOps[0];
          const isStringField = isStringType(field.type);
          const fieldSuggestions = suggestions[field.name] ?? [];
          const showSuggestions = openSuggestionField === field.name && fieldSuggestions.length > 0;

          return (
            <div key={field.name} className="relative">
              <div className={isStacked ? 'flex flex-wrap items-center gap-x-1.5 gap-y-[5px]' : 'flex flex-wrap items-center gap-2.5'}>
              <label
                htmlFor={`filter_${field.name}`}
                className={isStacked
                  ? 'w-full flex-none text-[12.5px] font-medium text-fg dark:text-fg-dark'
                  : 'w-[200px] flex-none text-[13px] font-medium text-fg dark:text-fg-dark'}
              >
                {field.name}
                <span className={`${isStacked ? 'ml-1.5 inline' : 'block'} font-mono text-[11px] font-normal text-fg-tertiary dark:text-fg-tertiary-dark`}>{field.type}</span>
              </label>
                <FormSelect
                  label={t('searchFilters.operatorFor', { field: field.name })}
                  labelClassName="sr-only"
                  id={`filter_operator_${field.name}`}
                  value={currentOp}
                  onChange={(e) => {
                    const newOp = e.target.value as MetadataOperator;
                    handleMetadataFilterChange(field.name, metadataFilters[field.name] || '', newOp);
                  }}
                  disabled={disabled}
                  options={allowedOps.map((op) => ({
                    value: op,
                    label: t(`searchFilters.operators.${OPERATOR_TRANSLATION_KEYS[op]}`),
                  }))}
                  className={isStacked ? 'w-[128px] shrink-0' : 'w-[150px] shrink-0'}
                />
                <div className={isStacked ? 'relative min-w-0 flex-1' : 'relative min-w-[140px] flex-1'}>
                  <FormField
                    label={field.name}
                    labelClassName="hidden"
                    id={`filter_${field.name}`}
                    value={metadataFilters[field.name] || ''}
                    onChange={(e) => {
                      if (isStringField) {
                        handleStringInputChange(field, e.target.value, currentOp);
                      } else {
                        handleMetadataFilterChange(field.name, e.target.value, currentOp);
                      }
                    }}
                    onBlur={() => handleInputBlur(field.name)}
                    onKeyDown={(e) => handleInputKeyDown(field.name, e)}
                    onFocus={() => {
                      if (fieldSuggestions.length > 0) setOpenSuggestionField(field.name);
                    }}
                    placeholder={currentOp === '$in'
                      ? t('searchFilters.multipleValuesPlaceholder')
                      : t('searchFilters.filterByField', { field: field.name })}
                    className="w-full"
                    disabled={disabled}
                  />
                  {showSuggestions && (
                    <div className="absolute z-10 mt-1 max-h-40 w-full overflow-y-auto rounded-lg border border-line bg-surface shadow-md dark:border-line-dark dark:bg-surface-dark">
                      {fieldSuggestions.map((s) => (
                        <button
                          key={s}
                          type="button"
                          onMouseDown={() => handleSuggestionClick(field.name, s)}
                          className="block w-full cursor-pointer px-3 py-1.5 text-left text-sm text-fg hover:bg-surface-hover dark:text-fg-dark dark:hover:bg-surface-hover-dark"
                        >
                          {s}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </div>
              {field.description && (
                <p className={`mt-1 text-xs text-fg-tertiary dark:text-fg-tertiary-dark ${isStacked ? '' : 'sm:pl-[210px]'}`}>{field.description}</p>
              )}
            </div>
          );
        })}
      </div>

      {/* FR-3.5 — Live JSON preview */}
      {filterMetadata && (
        <details className="mt-3">
          <summary className="cursor-pointer select-none text-xs text-fg-tertiary hover:text-fg-secondary dark:text-fg-tertiary-dark dark:hover:text-fg-secondary-dark">
            {t('searchFilters.jsonPreview')}
          </summary>
          <pre className="mt-1 overflow-x-auto rounded-md border border-line bg-surface p-2 text-xs leading-relaxed text-fg-secondary dark:border-line-dark dark:bg-surface-dark dark:text-fg-secondary-dark">
            {JSON.stringify(filterMetadata, null, 2)}
          </pre>
        </details>
      )}

      {/* FR-3.6 — Saved filters */}
      <div className={isStacked
        ? 'mt-4 flex flex-wrap items-center gap-2 border-t border-line pt-3.5 empty:hidden dark:border-line-dark'
        : 'mt-3 flex flex-wrap items-center gap-2'}
      >
        {filterMetadata && !showSaveForm && (
          <ButtonApp
            type="button"
            onClick={() => setShowSaveForm(true)}
            label={t('searchFilters.saveFilter')}
            variant="primary"
            size="medium"
          />
        )}
        {showSaveForm && (
          <div className="flex items-center gap-1">
            <FormField
              label={t('searchFilters.filterName')}
              labelClassName="sr-only"
              id="save-filter-name"
              value={saveFilterName}
              onChange={(e) => setSaveFilterName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleSaveFilter();
                if (e.key === 'Escape') { setShowSaveForm(false); setSaveFilterName(''); }
              }}
              placeholder={t('searchFilters.filterNamePlaceholder')}
              className="w-full"
            />
            <ButtonApp
              type="button"
              onClick={handleSaveFilter}
              disabled={!saveFilterName.trim()}
              label={t('save')}
              variant="primary"
              size="medium"
            />
            <ButtonApp
              type="button"
              onClick={() => { setShowSaveForm(false); setSaveFilterName(''); }}
              label={t('cancel')}
              variant="secondary"
              size="medium"
            />
          </div>
        )}
        {savedFilters.length > 0 && (
          <FormSelect
            label={t('searchFilters.loadSavedFilter')}
            labelClassName="sr-only"
            id="load-saved-filter"
            value={loadSelectValue}
            onChange={handleLoadFilter}
            options={[
              { value: '', label: t('searchFilters.loadSavedFilterOption') },
              ...savedFilters.map((filter) => ({ value: filter.id, label: filter.name })),
            ]}
            className="min-w-[220px] flex-1"
          />
        )}
      </div>

      {/* Load banner */}
      {loadedFilterName && (
        <div className="mt-2 flex items-center gap-2 rounded-md border border-bronze-border bg-bronze-bg px-2 py-1 text-xs text-bronze dark:border-bronze-border-dark dark:bg-bronze-bg-dark dark:text-bronze-dark">
          <span>
            {t('searchFilters.loaded')}: <strong>{loadedFilterName}</strong>
          </span>
          <ButtonApp
            type="button"
            onClick={() => { onFilterMetadataChange(undefined); setLoadedFilterName(null); }}
            label={t('searchFilters.clear')}
            variant="secondary"
            size="medium"
          />
          <ButtonApp
            type="button"
            onClick={handleRemoveLoadedFilter}
            label={t('delete')}
            variant="danger"
            size="medium"
          />
        </div>
      )}
    </div>
  );
}

export default SearchFilters;
