import { useEffect, useMemo, useState } from 'react';

export type MetadataOperator = '$eq' | '$ne' | '$gt' | '$gte' | '$lt' | '$lte';
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

interface SearchFiltersProps {
  metadataFields?: SearchFilterMetadataField[];
  dbType?: string;
  disabled?: boolean;
  onFilterMetadataChange: (filterMetadata: Record<string, unknown> | undefined) => void;
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
  },
  QDRANT: {
    $eq: 'match',
    $ne: 'must_not_match',
    $gt: 'gt',
    $gte: 'gte',
    $lt: 'lt',
    $lte: 'lte',
  },
};

function normalizeDbType(dbType?: string): SupportedDbType {
  if (dbType && dbType.toUpperCase() === 'QDRANT') {
    return 'QDRANT';
  }
  return DEFAULT_DB_TYPE;
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
        mustNot.push({
          key,
          match: { value },
        });
        break;
      case 'match':
        targetList.push({
          key,
          match: { value },
        });
        break;
      case 'gt':
      case 'gte':
      case 'lt':
      case 'lte':
        targetList.push({
          key,
          range: { [nativeOperator]: value },
        });
        break;
      default:
        targetList.push({
          key,
          match: { value },
        });
    }
  });

  const qdrantFilter: Record<string, unknown> = {};
  if (must.length > 0) {
    qdrantFilter.must = must;
  }
  if (should.length > 0) {
    qdrantFilter.should = should;
  }
  if (mustNot.length > 0) {
    qdrantFilter.must_not = mustNot;
  }

  return Object.keys(qdrantFilter).length > 0 ? qdrantFilter : undefined;
}

function convertMetadataValue(fieldType: string, rawValue: string): unknown {
  switch (fieldType) {
    case 'int': {
      const parsed = parseInt(rawValue, 10);
      return Number.isNaN(parsed) ? rawValue : parsed;
    }
    case 'float': {
      const parsed = parseFloat(rawValue);
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
    if (!trimmedValue) {
      return;
    }

    const selectedOperator = filterOperators[fieldName] || '$eq';
    const nativeOperator = operatorMapping[selectedOperator];
    if (!nativeOperator) {
      return;
    }

    const fieldDefinition = metadataFields?.find((field) => field.name === fieldName);
    const convertedValue = fieldDefinition ? convertMetadataValue(fieldDefinition.type, trimmedValue) : trimmedValue;

    prepared.push({
      fieldName,
      operator: selectedOperator,
      nativeOperator,
      value: convertedValue,
    });
  });

  return prepared;
}

export function SearchFilters({
  metadataFields,
  dbType,
  disabled = false,
  onFilterMetadataChange,
}: SearchFiltersProps) {
  const [metadataFilters, setMetadataFilters] = useState<Record<string, string>>({});
  const [filterOperators, setFilterOperators] = useState<Record<string, MetadataOperator>>({});
  const [logicalOperator, setLogicalOperator] = useState<'$and' | '$or'>('$and');

  useEffect(() => {
    setMetadataFilters({});
    setFilterOperators({});
    setLogicalOperator('$and');
  }, [metadataFields]);

  useEffect(() => {
    if (!metadataFields || metadataFields.length === 0) {
      onFilterMetadataChange(undefined);
    }
  }, [metadataFields, onFilterMetadataChange]);

  const normalizedDbType = useMemo(() => normalizeDbType(dbType), [dbType]);
  const operatorMapping = FILTER_OPERATOR_MAPPINGS[normalizedDbType];

  useEffect(() => {
    const prepared = prepareFilters(metadataFilters, filterOperators, metadataFields, operatorMapping);
    const filterMetadata = normalizedDbType === 'QDRANT'
      ? buildQdrantFilter(prepared, logicalOperator)
      : buildPgvectorFilter(prepared, logicalOperator);

    onFilterMetadataChange(filterMetadata);
  }, [metadataFilters, filterOperators, logicalOperator, metadataFields, normalizedDbType, operatorMapping, onFilterMetadataChange]);

  const handleMetadataFilterChange = (fieldName: string, value: string, operator: MetadataOperator) => {
    setMetadataFilters((prev) => ({
      ...prev,
      [fieldName]: value,
    }));
    setFilterOperators((prev) => ({
      ...prev,
      [fieldName]: operator,
    }));
  };

  if (!metadataFields || metadataFields.length === 0) {
    return null;
  }

  return (
    <div className="border border-gray-200 rounded-lg p-4 bg-gray-50">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-medium text-gray-700">
          <span className="mr-2" aria-hidden="true">🔍</span>{' '}
          Filter by Metadata
        </h3>
        <div className="flex items-center gap-2">
          <label htmlFor="logicalOperator" className="text-sm text-gray-600">
            Match:
          </label>
          <select
            id="logicalOperator"
            value={logicalOperator}
            onChange={(e) => setLogicalOperator(e.target.value as '$and' | '$or')}
            className="px-3 py-1 border border-gray-300 rounded-lg text-sm font-medium bg-white"
            disabled={disabled}
          >
            <option value="$and">ALL filters (AND)</option>
            <option value="$or">ANY filter (OR)</option>
          </select>
        </div>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {metadataFields.map((field) => {
          const operator = filterOperators[field.name] || '$eq';
          return (
            <div key={field.name}>
              <label htmlFor={`filter_${field.name}`} className="block text-sm font-medium text-gray-700 mb-1">
                {field.name}
                <span className="text-xs text-gray-500 ml-1">({field.type})</span>
              </label>
              <div className="flex items-center gap-2">
                <select
                  value={operator}
                  onChange={(e) => handleMetadataFilterChange(field.name, metadataFilters[field.name] || '', e.target.value as MetadataOperator)}
                  className="px-2 py-1 border border-gray-300 rounded-lg text-sm"
                  disabled={disabled}
                >
                  <option value="$eq">equals</option>
                  <option value="$ne">not equals</option>
                  <option value="$gt">greater than</option>
                  <option value="$gte">greater than or equal</option>
                  <option value="$lt">less than</option>
                  <option value="$lte">less than or equal</option>
                </select>
                <input
                  type="text"
                  id={`filter_${field.name}`}
                  value={metadataFilters[field.name] || ''}
                  onChange={(e) => handleMetadataFilterChange(field.name, e.target.value, operator)}
                  placeholder={`Filter by ${field.name}`}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-yellow-500 focus:border-transparent text-sm"
                  disabled={disabled}
                />
              </div>
              {field.description && (
                <p className="text-xs text-gray-500 mt-1">{field.description}</p>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default SearchFilters;
