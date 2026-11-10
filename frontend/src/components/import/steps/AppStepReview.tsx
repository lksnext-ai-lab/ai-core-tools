import Alert from '../../ui/Alert';
import type {
  AppImportPreview,
  ConflictMode,
} from '../../../types/import';
import {
  COMPONENT_TYPE_ICONS,
} from '../../../types/import';
import Table, { type TableColumn } from '../../ui/Table';
import { Badge } from '../../ui/Badge';
import CardApp from '../../ui/CardApp';
import { useTranslation } from 'react-i18next';

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
  apiKeyStatus?: 'provided' | 'placeholder';
};

type ReviewSkippedItem = {
  icon: string;
  type: string;
  name: string;
};

const COMPONENT_TYPE_TRANSLATION_KEYS: Record<string, string> = {
  ai_service: 'aiServices',
  embedding_service: 'embeddingServices',
  output_parser: 'outputParsers',
  mcp_config: 'mcpConfigs',
  silo: 'silos',
  repository: 'repositories',
  domain: 'domains',
  agent: 'agents',
  app: 'apps',
};

function getApiKeyStatus(
  needsApiKey: boolean,
  componentName: string,
  apiKeys: Record<string, string>
): ReviewSelectedItem['apiKeyStatus'] {
  if (!needsApiKey) return undefined;
  return apiKeys[componentName] ? 'provided' : 'placeholder';
}

function buildReviewRows(
  preview: AppImportPreview,
  selection: Record<string, boolean>,
  apiKeys: Record<string, string>,
  translateComponentType: (type: string) => string,
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
      const typeLabel = translateComponentType(cat.type);

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
  const { t } = useTranslation('common');
  const translateComponentType = (type: string) => {
    const translationKey = COMPONENT_TYPE_TRANSLATION_KEYS[type];
    return translationKey
      ? t(`importModal.appUpload.components.${translationKey}`, { count: 1 })
      : t('importModal.unknown');
  };
  const { selectedItems, skippedItems } = buildReviewRows(
    preview,
    selection,
    apiKeys,
    translateComponentType,
  );
  const selectedColumns: TableColumn<ReviewSelectedItem>[] = [
    {
      header: t('importModal.agentReview.columns.component'),
      render: (row) => (
        <>
          <span className="mr-1 text-sm">{row.icon}</span>
          {row.type}
        </>
      ),
    },
    {
      header: t('importModal.agentReview.columns.name'),
      accessor: 'name',
      className: 'px-6 py-4 text-xs text-fg-secondary dark:text-fg-secondary-dark',
    },
    {
      header: t('importModal.agentReview.columns.action'),
      render: (row) => (
        <>
          <Badge label={t('importModal.actions.import')} variant="success" />
          {row.apiKeyStatus && (
            <Badge
              label={t('importModal.appReview.apiKeyLabel', {
                status: t(`importModal.appReview.apiKeyStatus.${row.apiKeyStatus}`),
              })}
              variant={row.apiKeyStatus === 'provided' ? 'info' : 'warning'}
              className="ml-1"
            />
          )}
        </>
      ),
    },
  ];

  return (
    <div className="space-y-4">
      <h4 className="font-display text-[17px] font-medium leading-8 text-fg dark:text-fg-dark">
        {t('importModal.result.summary')}
      </h4>

      <CardApp variant="canvas" className="p-3">
        <p >
          <span className="text-sm uppercase text-bronze-dark">{t('importModal.appReview.appName')}:</span>{' '}
          <span className="text-sm text-fg dark:text-fg-dark">{appName}</span>
        </p>
        <p >
          <span className="text-sm uppercase text-bronze-dark">{t('importModal.appReview.conflictMode')}:</span>{' '}
          <span className="text-sm text-fg dark:text-fg-dark">
            {t(`importModal.conflict.options.${conflictMode}`)}
          </span>
        </p>
        <p >
          <span className="text-sm uppercase text-bronze-dark">{t('importModal.appReview.componentsToImport')}:
          </span>{' '}
          <span className="text-sm text-fg dark:text-fg-dark">{selectedItems.length}</span>
        </p>
      </CardApp>

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
            {t('importModal.appReview.skipped', { count: skippedItems.length })}
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
          title={t('importModal.result.warnings')}
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
