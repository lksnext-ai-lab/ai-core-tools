import { type ChangeEvent } from 'react';
import Alert from '../../ui/Alert';
import type { AgentImportPreview } from '../../../types/import';
import {
  COMPONENT_TYPE_ICONS,
} from '../../../types/import';
import { FormField } from '../../ui/FormField';
import { LoadingState } from '../../ui/LoadingState';
import CardApp from '../../ui/CardApp';
import { useTranslation } from 'react-i18next';

interface Props {
  file: File | null;
  onFileSelect: (file: File) => void;
  preview: AgentImportPreview | null;
  isValidating: boolean;
  validationError: string | null;
}

function AgentStepUpload({
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

  type InventoryItem = { label: string; icon: string; name: string };

  const inventoryItems = (
    preview
      ? [
          preview.ai_service && {
            label: t('importModal.agentUpload.components.aiService'),
            icon: COMPONENT_TYPE_ICONS.ai_service,
            name: preview.ai_service.component_name,
          },
          preview.silo && {
            label: t('importModal.agentUpload.components.silo'),
            icon: COMPONENT_TYPE_ICONS.silo,
            name: preview.silo.component_name,
          },
          preview.output_parser && {
            label: t('importModal.agentUpload.components.outputParser'),
            icon: COMPONENT_TYPE_ICONS.output_parser,
            name: preview.output_parser.component_name,
          },
          preview.mcp_configs.length > 0 && {
            label: t('importModal.agentUpload.components.mcpConfigs', {
              count: preview.mcp_configs.length,
            }),
            icon: COMPONENT_TYPE_ICONS.mcp_config,
            name: preview.mcp_configs
              .map((m) => m.component_name)
              .join(', '),
          },
          preview.agent_tools.length > 0 && {
            label: t('importModal.agentUpload.components.agentTools', {
              count: preview.agent_tools.length,
            }),
            icon: COMPONENT_TYPE_ICONS.agent,
            name: preview.agent_tools
              .map((t) => t.component_name)
              .join(', '),
          },
        ]
      : []
  ).filter((item): item is InventoryItem => Boolean(item));

  return (
    <div className="space-y-4">
      <FormField
        id="agent-export-file-input"
        label={t('importModal.agentUpload.selectExportFile')}
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
          message={t('importModal.agentUpload.validating')}
        />
      )}

      {validationError && (
        <Alert type="error" message={validationError} />
      )}

      {preview && (
        <CardApp
          variant="canvas"
          className="p-4"
          titulo={t('importModal.agentUpload.summary')}
        >
          <div className="flex items-top space-x-3">
            <span className="text-md text-bronze dark:text-bronze-dark">
              {COMPONENT_TYPE_ICONS.agent}
            </span>
            <div>
              <p className="font-xs text-fg dark:text-fg-dark">
                {preview.agent.component_name}
              </p>
              <p className="text-xs text-fg-secondary dark:text-fg-secondary-dark">
                {t('importModal.agentUpload.version', {
                  version: preview.export_version,
                })}
              </p>
            </div>
          </div>

          {inventoryItems.length > 0 && (
            <div className="border-t border-line dark:border-line-dark pt-3">
              <p className="text-md font-medium text-fg dark:text-fg-dark mb-2">
                {t('importModal.agentUpload.bundledComponents')}
              </p>
              <div className="space-y-1">
                {inventoryItems.map((item) => (
                  <div
                    key={item.label}
                    className="flex items-center text-sm text-md text-bronze dark:text-bronze-dark"
                  >
                    <span className="mr-2">{item.icon}</span>
                    <span className="font-medium mr-1">
                      {item.label}:
                    </span>
                    <span className="text-fg dark:text-fg-dark">{item.name}</span>
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

export default AgentStepUpload;
