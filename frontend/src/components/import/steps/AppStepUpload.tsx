import { type ChangeEvent } from 'react';
import Alert from '../../ui/Alert';
import type { AppImportPreview } from '../../../types/import';
import { COMPONENT_TYPE_ICONS } from '../../../types/import';
import { FormField } from '../../ui/FormField';
import { LoadingState } from '../../ui/LoadingState';
import CardApp from '../../ui/CardApp';
import { useTranslation } from 'react-i18next';

interface Props {
  file: File | null;
  onFileSelect: (file: File) => void;
  preview: AppImportPreview | null;
  isValidating: boolean;
  validationError: string | null;
}

function AppStepUpload({
  file,
  onFileSelect,
  preview,
  isValidating,
  validationError,
}: Readonly<Props>) {
  const { t } = useTranslation('common');

  const handleFileChange = (e: ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (f) onFileSelect(f);
  };

  const countRows = preview
    ? [
        {
          key: 'aiServices',
          icon: COMPONENT_TYPE_ICONS.ai_service,
          label: t('importModal.appUpload.components.aiServices', {
            count: preview.component_counts.ai_services ?? 0,
          }),
          count: preview.component_counts.ai_services ?? 0,
        },
        {
          key: 'embeddingServices',
          icon: COMPONENT_TYPE_ICONS.embedding_service,
          label: t('importModal.appUpload.components.embeddingServices', {
            count: preview.component_counts.embedding_services ?? 0,
          }),
          count:
            preview.component_counts.embedding_services ?? 0,
        },
        {
          key: 'outputParsers',
          icon: COMPONENT_TYPE_ICONS.output_parser,
          label: t('importModal.appUpload.components.outputParsers', {
            count: preview.component_counts.output_parsers ?? 0,
          }),
          count:
            preview.component_counts.output_parsers ?? 0,
        },
        {
          key: 'mcpConfigs',
          icon: COMPONENT_TYPE_ICONS.mcp_config,
          label: t('importModal.appUpload.components.mcpConfigs', {
            count: preview.component_counts.mcp_configs ?? 0,
          }),
          count: preview.component_counts.mcp_configs ?? 0,
        },
        {
          key: 'silos',
          icon: COMPONENT_TYPE_ICONS.silo,
          label: t('importModal.appUpload.components.silos', {
            count: preview.component_counts.silos ?? 0,
          }),
          count: preview.component_counts.silos ?? 0,
        },
        {
          key: 'repositories',
          icon: COMPONENT_TYPE_ICONS.repository,
          label: t('importModal.appUpload.components.repositories', {
            count: preview.component_counts.repositories ?? 0,
          }),
          count:
            preview.component_counts.repositories ?? 0,
        },
        {
          key: 'domains',
          icon: COMPONENT_TYPE_ICONS.domain,
          label: t('importModal.appUpload.components.domains', {
            count: preview.component_counts.domains ?? 0,
          }),
          count: preview.component_counts.domains ?? 0,
        },
        {
          key: 'agents',
          icon: COMPONENT_TYPE_ICONS.agent,
          label: t('importModal.appUpload.components.agents', {
            count: preview.component_counts.agents ?? 0,
          }),
          count: preview.component_counts.agents ?? 0,
        },
      ].filter((r) => r.count > 0)
    : [];

  return (
    <div className="space-y-4">
      <FormField
        id="app-export-file-input"
        label={t('importModal.appUpload.selectExportFile')}
        type="file"
        accept=".json,application/json"
        fileName={file?.name}
        fileButtonLabel={t('importModal.file.choose')}
        noFileSelectedLabel={t('importModal.file.noFileSelected')}
        onChange={handleFileChange}
        disabled={isValidating}
      />

      {isValidating && (
        <LoadingState
          variant="inline"
          message={t('importModal.appUpload.validating')}
        />
      )}

      {validationError && (
        <Alert type="error" message={validationError} />
      )}

      {preview && (
        <CardApp
          variant="canvas"
          className="p-4"
          titulo={t('importModal.appUpload.summary')}
        >
          <div className="flex items-top space-x-3">
            <span className="text-md text-bronze dark:text-bronze-dark">
              {COMPONENT_TYPE_ICONS.app}
            </span>
            <div>
              <p className="font-xs text-fg dark:text-fg-dark">
                {preview.app_name}
              </p>
              <p className="text-xs text-fg-secondary dark:text-fg-secondary-dark">
                {t('importModal.appUpload.version', {
                  version: preview.export_version,
                })}
              </p>
            </div>
          </div>

          {countRows.length > 0 && (
            <div className="border-t border-line dark:border-line-dark pt-3">
              <p className="text-md font-medium text-fg dark:text-fg-dark mb-2">
                {t('importModal.appUpload.componentInventory')}
              </p>
              <div className="grid grid-cols-2 gap-1">
                {countRows.map((r) => (
                  <div
                    key={r.key}
                    className="flex items-center text-sm text-md text-bronze dark:text-bronze-dark"
                  >
                    <span className="mr-2">{r.icon}</span>
                    <span className="text-sm text-fg dark:text-fg-dark">
                      {r.count} {r.label}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {preview.global_warnings.length > 0 && (
            <Alert
              type="warning"
              message={
                <ul className="list-disc list-inside space-y-1">
                  {preview.global_warnings.map((w) => (
                    <li key={w}>{w}</li>
                  ))}
                </ul>
              }
            />
          )}
        </CardApp>
      )}
    </div>
  );
}

export default AppStepUpload;
