import Alert from '../../ui/Alert';
import type {
  AppImportPreview,
  ConflictMode,
} from '../../../types/import';
import {
  COMPONENT_TYPE_ICONS,
  COMPONENT_TYPE_LABELS,
} from '../../../types/import';

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
      <h4 className="text-sm font-medium text-gray-900">
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
        <div className="border border-gray-200 rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                  Component
                </th>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                  Name
                </th>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                  Action
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {selectedItems.map((row) => (
                <tr
                  key={`${row.type}:${row.name}`}
                >
                  <td className="px-4 py-2 whitespace-nowrap">
                    <span className="mr-1">
                      {row.icon}
                    </span>
                    {row.type}
                  </td>
                  <td className="px-4 py-2 font-medium text-gray-900">
                    {row.name}
                  </td>
                  <td className="px-4 py-2">
                    <span className="inline-flex px-2 py-0.5 text-xs rounded-full font-medium bg-green-100 text-green-700">
                      Import
                    </span>
                    {row.apiKeyStatus && (
                      <span
                        className={`ml-1 inline-flex px-2 py-0.5 text-xs rounded-full font-medium ${
                          row.apiKeyStatus === 'Provided'
                            ? 'bg-blue-100 text-blue-700'
                            : 'bg-amber-100 text-amber-700'
                        }`}
                      >
                        Key: {row.apiKeyStatus}
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
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
