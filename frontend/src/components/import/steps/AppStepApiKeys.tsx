import Alert from '../../ui/Alert';
import type { AppImportPreview } from '../../../types/import';
import { COMPONENT_TYPE_ICONS } from '../../../types/import';

interface Props {
  preview: AppImportPreview;
  selection: Record<string, boolean>;
  apiKeys: Record<string, string>;
  onApiKeyChange: (serviceName: string, key: string) => void;
}

function AppStepApiKeys({
  preview,
  selection,
  apiKeys,
  onApiKeyChange,
}: Props) {
  // Collect all selected services that need API keys
  const servicesNeedingKeys = [
    ...preview.ai_services,
    ...preview.embedding_services,
  ].filter((svc) => {
    const key = `${svc.component_type}:${svc.component_name}`;
    return selection[key] && svc.needs_api_key;
  });

  if (servicesNeedingKeys.length === 0) {
    return (
      <Alert
        type="info"
        message="No selected services require API key configuration. You can proceed."
      />
    );
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-gray-600">
        Optionally provide API keys for the selected services.
        You can also configure them later after import.
      </p>

      <div className="space-y-3">
        {servicesNeedingKeys.map((svc) => (
          <div
            key={`${svc.component_type}:${svc.component_name}`}
            className="bg-gray-50 border border-gray-200 rounded-lg p-4"
          >
            <div className="flex items-center space-x-2 mb-2">
              <span>
                {COMPONENT_TYPE_ICONS[svc.component_type]}
              </span>
              <span className="text-sm font-medium text-gray-900">
                {svc.component_name}
              </span>
              {svc.provider && (
                <span className="text-xs text-gray-500">
                  ({svc.provider})
                </span>
              )}
            </div>
            <input
              type="password"
              placeholder="API key (optional)"
              value={apiKeys[svc.component_name] || ''}
              onChange={(e) =>
                onApiKeyChange(
                  svc.component_name,
                  e.target.value
                )
              }
              className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
        ))}
      </div>

      <Alert
        type="info"
        message='Services without API keys will use the placeholder value "CHANGE_ME" and must be configured after import.'
      />
    </div>
  );
}

export default AppStepApiKeys;
