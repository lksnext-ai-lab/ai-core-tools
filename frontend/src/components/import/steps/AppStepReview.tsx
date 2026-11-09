import Alert from '../../ui/Alert';
import type {
  AppImportPreview,
  ConflictMode,
} from '../../../types/import';
import {
  COMPONENT_TYPE_ICONS,
  COMPONENT_TYPE_LABELS,
} from '../../../types/import';
import Table, { type TableColumn } from '../../ui/Table';
import { Badge } from '../../ui/Badge';

interface Props {
  preview: AppImportPreview;
  appName: string;
  conflictMode: ConflictMode;
  selection: Record<string, boolean>;
  apiKeys: Record<string, string>;
}

type ReviewSelectedItem = {
  icon: string;
  type: string;
  name: string;
  apiKeyStatus?: string;
};

type ReviewSkippedItem = {
  icon: string;
  type: string;
  name: string;
};

const selectedColumns: TableColumn<ReviewSelectedItem>[] = [
  {
    header: 'Component',
    render: (row) => (
      <>
        <span className="mr-1">{row.icon}</span>
        {row.type}
      </>
    ),
  },
  {
    header: 'Name',
    accessor: 'name',
    className: 'px-6 py-4 text-fg dark:text-fg-dark',
  },
  {
    header: 'Action',
    render: (row) => (
      <>
        <Badge label="Import" variant="success" />
        {row.apiKeyStatus && (
          <Badge
            label={`Key: ${row.apiKeyStatus}`}
            variant={row.apiKeyStatus === 'Provided' ? 'info' : 'warning'}
            className="ml-1"
          />
        )}
      </>
    ),
  },
];

function getApiKeyStatus(
  needsApiKey: boolean,
  componentName: string,
  apiKeys: Record<string, string>
): string | undefined {
  if (!needsApiKey) return undefined;
  return apiKeys[componentName] ? 'Provided' : 'CHANGE_ME';
}

function buildReviewRows(
  preview: AppImportPreview,
  selection: Record<string, boolean>,
  apiKeys: Record<string, string>
): { selectedItems: ReviewSelectedItem[]; skippedItems: ReviewSkippedItem[] } {
  const categories = [
    { type: 'ai_service', items: preview.ai_services },
    { type: 'embedding_service', items: preview.embedding_services },
    { type: 'output_parser', items: preview.output_parsers },
    { type: 'mcp_config', items: preview.mcp_configs },
    { type: 'silo', items: preview.silos },
    { type: 'repository', items: preview.repositories },
    { type: 'domain', items: preview.domains },
    { type: 'agent', items: preview.agents },
  ];

  const selectedItems: ReviewSelectedItem[] = [];
  const skippedItems: ReviewSkippedItem[] = [];

  for (const cat of categories) {
    for (const item of cat.items) {
      const key = `${cat.type}:${item.component_name}`;
      const icon = COMPONENT_TYPE_ICONS[cat.type] || '';
      const typeLabel = COMPONENT_TYPE_LABELS[cat.type] || cat.type;

      if (selection[key]) {
        const apiKeyStatus = getApiKeyStatus(
          item.needs_api_key,
          item.component_name,
          apiKeys
        );
        selectedItems.push({ icon, type: typeLabel, name: item.component_name, apiKeyStatus });
      } else {
        skippedItems.push({ icon, type: typeLabel, name: item.component_name });
      }
    }
  }

  return { selectedItems, skippedItems };
}

function AppStepReview({
  preview,
  appName,
  conflictMode,
  selection,
  apiKeys,
}: Readonly<Props>) {
  const { selectedItems, skippedItems } = buildReviewRows(
    preview,
    selection,
    apiKeys
  );

  return (
    <div className="space-y-4">
      <h4 className="font-display text-[17px] font-medium leading-8 text-fg dark:text-fg-dark">
        Import Summary
      </h4>

      <div className="bg-blue-50 border border-blue-200 rounded-lg p-3">
        <p className="text-sm text-blue-900">
          <span className="font-medium">App Name:</span>{' '}
          {appName}
        </p>
        <p className="text-sm text-blue-900">
          <span className="font-medium">Conflict Mode:</span>{' '}
          {conflictMode}
        </p>
        <p className="text-sm text-blue-900">
          <span className="font-medium">
            Components to Import:
          </span>{' '}
          {selectedItems.length}
        </p>
      </div>

      {/* Selected components table */}
      {selectedItems.length > 0 && (
        <Table
          columns={selectedColumns}
          data={selectedItems}
          keyExtractor={(row) => `${row.type}:${row.name}`}
        />
      )}

      {/* Skipped components */}
      {skippedItems.length > 0 && (
        <div>
          <p className="text-xs font-medium text-gray-500 mb-1">
            Skipped ({skippedItems.length})
          </p>
          <div className="text-xs text-gray-400 space-y-0.5">
            {skippedItems.map((row) => (
              <p key={`${row.type}:${row.name}`}>
                {row.icon} {row.type}: {row.name}
              </p>
            ))}
          </div>
        </div>
      )}

      {preview.global_warnings.length > 0 && (
        <Alert
          type="warning"
          title="Warnings"
          message={
            <ul className="list-disc list-inside space-y-1">
              {preview.global_warnings.map((w) => (
                <li key={w}>{w}</li>
              ))}
            </ul>
          }
        />
      )}
    </div>
  );
}

export default AppStepReview;
