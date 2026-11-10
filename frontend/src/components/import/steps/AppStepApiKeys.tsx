import Alert from '../../ui/Alert';
import { FormField } from '../../ui/FormField';
import { useTranslation } from 'react-i18next';
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
}: Readonly<Props>) {
  const { t } = useTranslation('common');

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
        message={t('importModal.appApiKeys.noSelectedServices')}
      />
    );
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-fg dark:text-fg-dark">
        {t('importModal.appApiKeys.description')}
      </p>

      <div className="space-y-3">
        {servicesNeedingKeys.map((svc) => (
          <div
            key={`${svc.component_type}:${svc.component_name}`}
            className="p-4"
          >
            <div className="flex items-center space-x-2 mb-2">
              <span className="text-md text-bronze-dark">
                {COMPONENT_TYPE_ICONS[svc.component_type]}
              </span>
              <span className="text-sm font-medium text-fg dark:text-fg-dark">
                {svc.component_name}
              </span>
              {svc.provider && (
                <span className="text-xs text-fg-secondary dark:text-fg-secondary-dark">
                  ({svc.provider})
                </span>
              )}
            </div>
            <FormField
              id={`api-key-${svc.component_type}-${svc.component_name}`}
              type="password"
              ariaLabel={t('importModal.appApiKeys.keyLabel', {
                service: svc.component_name,
              })}
              placeholder={t('importModal.appApiKeys.keyPlaceholder')}
              value={apiKeys[svc.component_name] || ''}
              onChange={(e) => onApiKeyChange(svc.component_name, e.target.value)}
            />
          </div>
        ))}
      </div>

      <Alert
        type="info"
        message={t('importModal.appApiKeys.missingKeysInfo')}
      />
    </div>
  );
}

export default AppStepApiKeys;
