import { Bot, Database, Plug, Webhook } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { Trans, useTranslation } from 'react-i18next';
import Alert from '../../ui/Alert';
import type { AgentImportPreview } from '../../../types/import';
import { ServiceOptionStatus, serviceStatusId } from '../../ui/ServiceOptionStatus';
import { FormSelect } from '../../ui/FormField';
import type { ServiceOptionLike } from '../../../utils/serviceLifecycle';
import { selectableServiceOptions, serviceOptionLabel } from '../../../utils/serviceLifecycle';
import CardApp from '../../ui/CardApp';
import { Badge } from '../../ui/Badge';
import { FormField } from '../../ui/FormField';

interface Props {
  preview: AgentImportPreview;
  useExistingAIService: boolean;
  onUseExistingAIServiceChange: (val: boolean) => void;
  selectedAIServiceId: number | null;
  onSelectedAIServiceIdChange: (id: number | null) => void;
  availableAIServices: readonly ServiceOptionLike[];
  importBundledSilo: boolean;
  onImportBundledSiloChange: (val: boolean) => void;
  importBundledOutputParser: boolean;
  onImportBundledOutputParserChange: (val: boolean) => void;
  importBundledMCPConfigs: boolean;
  onImportBundledMCPConfigsChange: (val: boolean) => void;
  importBundledAgentTools: boolean;
  onImportBundledAgentToolsChange: (val: boolean) => void;
}

function DepCard({
  icon,
  title,
  badge,
  badgeVariant,
  children,
}: Readonly<{
  icon: LucideIcon;
  title: string;
  badge: string;
  badgeVariant: 'error' | 'default';
  children: React.ReactNode;
}>) {
  return (
    <CardApp
      className="p-4 space-y-3"
      icon={icon}
      titulo={title}
      headerExtra={(
        <Badge label={badge} variant={badgeVariant} />
      )}
    >
      {children}
    </CardApp>
  );
}

function AgentStepDeps({
  preview,
  useExistingAIService,
  onUseExistingAIServiceChange,
  selectedAIServiceId,
  onSelectedAIServiceIdChange,
  availableAIServices,
  importBundledSilo,
  onImportBundledSiloChange,
  importBundledOutputParser,
  onImportBundledOutputParserChange,
  importBundledMCPConfigs,
  onImportBundledMCPConfigsChange,
  importBundledAgentTools,
  onImportBundledAgentToolsChange,
}: Readonly<Props>) {
  const { t } = useTranslation('common');
  const aiServiceOptions = [
    { value: '', label: t('importModal.agentDependencies.selectAIService') },
    ...selectableServiceOptions(availableAIServices, undefined).map((service) => ({
      value: service.service_id,
      label: serviceOptionLabel(service),
    })),
  ];

  return (
    <div className="space-y-4">
      <p className="text-sm text-fg dark:text-fg-dark">
        {t('importModal.agentDependencies.description')}
      </p>

      <DepCard
        icon={Bot}
        title={t('importModal.agentUpload.components.aiService')}
        badge={t('importModal.agentDependencies.required')}
        badgeVariant="error"
      >
        {preview.ai_service ? (
          <>
            <div className="space-y-2">
              <FormField
                type="radio"
                id="agent-import-ai-service-bundled"
                name="ai_service_source"
                value="bundled"
                className="flex items-center gap-2"
                labelClassName="text-sm text-fg dark:text-fg-dark"
                checked={!useExistingAIService}
                onChange={() =>
                  onUseExistingAIServiceChange(false)
                }
                label={(
                  <>
                    <Trans
                      i18nKey="importModal.agentDependencies.importBundledAIService"
                      values={{ name: preview.ai_service.component_name }}
                      components={{ strong: <strong /> }}
                    />
                    {preview.ai_service.provider && (
                      <span className="text-fg-secondary dark:text-fg-secondary-dark ml-1">
                        ({preview.ai_service.provider})
                      </span>
                    )}
                  </>
                )}
              />
              <FormField
                type="radio"
                id="agent-import-ai-service-existing"
                name="ai_service_source"
                value="existing"
                className="flex items-center gap-2"
                labelClassName="text-sm text-fg dark:text-fg-dark"
                checked={useExistingAIService}
                onChange={() =>
                  onUseExistingAIServiceChange(true)
                }
                label={t('importModal.agentDependencies.useExistingAIService')}
              />
            </div>
            {useExistingAIService && (
              <FormSelect
                label={t('importModal.agentUpload.components.aiService')}
                value={selectedAIServiceId ?? ''}
                options={aiServiceOptions}
                onChange={(e) =>
                  onSelectedAIServiceIdChange(
                    e.target.value
                      ? Number(e.target.value)
                      : null
                  )
                }
                id="agent-import-ai-service"
                ariaDescribedBy={serviceStatusId(availableAIServices, selectedAIServiceId, 'agent-import-ai-service')}
                className="mt-2"
                labelClassName="sr-only"
              />
            )}
            {useExistingAIService && (
              <ServiceOptionStatus
                options={availableAIServices}
                selectedId={selectedAIServiceId}
                selectId="agent-import-ai-service"
              />
            )}
            {!useExistingAIService && (
              <CardApp variant="canvas" className="text-xs text-bronze dark:text-bronze-dark">
                {t('importModal.agentDependencies.apiKeyWarning')}
              </CardApp>
            )}
          </>
        ) : (
          <>
            <Alert
              type="warning"
              message={t('importModal.agentDependencies.missingAIService', {
                name: preview.agent.component_name,
              })}
            />
            <FormSelect
              label={t('importModal.agentUpload.components.aiService')}
              value={selectedAIServiceId ?? ''}
              options={aiServiceOptions}
              onChange={(e) =>
                onSelectedAIServiceIdChange(
                  e.target.value
                    ? Number(e.target.value)
                    : null
                )
              }
              id="agent-import-ai-service-required"
              ariaDescribedBy={serviceStatusId(availableAIServices, selectedAIServiceId, 'agent-import-ai-service-required')}
              labelClassName="sr-only"
            />
            <ServiceOptionStatus
              options={availableAIServices}
              selectedId={selectedAIServiceId}
              selectId="agent-import-ai-service-required"
            />
          </>
        )}
      </DepCard>

      {preview.silo && (
        <DepCard
          icon={Database}
          title={t('importModal.agentDependencies.siloTitle')}
          badge={t('importModal.agentDependencies.optional')}
          badgeVariant="default"
        >
          <FormField
            type="checkbox"
            id="import-bundled-silo"
            checked={importBundledSilo}
            onChange={(e) =>
              onImportBundledSiloChange(e.target.checked)
            }
            className="flex items-center gap-2"
            labelClassName="text-sm text-fg dark:text-fg-dark"
            label={t('importModal.agentDependencies.importComponent', {
              name: preview.silo.component_name,
            })}
          />
          {preview.silo_embedding_service && importBundledSilo && (
            <p className="text-xs text-fg-secondary dark:text-fg-secondary-dark ml-6">
              {t('importModal.agentDependencies.includesEmbeddingService', {
                name: preview.silo_embedding_service.component_name,
              })}
            </p>
          )}
          {preview.silo_output_parser && importBundledSilo && (
            <p className="text-xs text-fg-secondary dark:text-fg-secondary-dark ml-6">
              {t('importModal.agentDependencies.includesOutputParser', {
                name: preview.silo_output_parser.component_name,
              })}
            </p>
          )}
        </DepCard>
      )}

      {preview.output_parser && (
        <DepCard
          icon={Webhook}
          title={t('importModal.agentUpload.components.outputParser')}
          badge={t('importModal.agentDependencies.optional')}
          badgeVariant="default"
        >
          <FormField
            type="checkbox"
            id="import-bundled-output-parser"
            checked={importBundledOutputParser}
            onChange={(e) =>
              onImportBundledOutputParserChange(
                e.target.checked
              )
            }
            className="flex items-center gap-2"
            labelClassName="text-sm text-fg dark:text-fg-dark"
            label={t('importModal.agentDependencies.importComponent', {
              name: preview.output_parser.component_name,
            })}
          />
        </DepCard>
      )}

      {preview.mcp_configs.length > 0 && (
        <DepCard
          icon={Plug}
          title={t('importModal.agentUpload.components.mcpConfigs', {
            count: preview.mcp_configs.length,
          })}
          badge={t('importModal.agentDependencies.optional')}
          badgeVariant="default"
        >
          <FormField
            type="checkbox"
            id="import-bundled-mcp-configs"
            checked={importBundledMCPConfigs}
            onChange={(e) =>
              onImportBundledMCPConfigsChange(
                e.target.checked
              )
            }
            className="flex items-center gap-2"
            labelClassName="text-sm text-fg dark:text-fg-dark"
            label={t('importModal.agentDependencies.importAllMCPConfigs')}
          />
          <ul className="ml-6 text-xs text-fg-secondary dark:text-fg-secondary-dark space-y-0.5">
            {preview.mcp_configs.map((m) => (
              <li key={m.component_name}>
                {m.component_name}
              </li>
            ))}
          </ul>
        </DepCard>
      )}

      {preview.agent_tools.length > 0 && (
        <DepCard
          icon={Bot}
          title={t('importModal.agentUpload.components.agentTools', {
            count: preview.agent_tools.length,
          })}
          badge={t('importModal.agentDependencies.optional')}
          badgeVariant="default"
        >
          <FormField
            type="checkbox"
            id="import-bundled-agent-tools"
            checked={importBundledAgentTools}
            onChange={(e) =>
              onImportBundledAgentToolsChange(
                e.target.checked
              )
            }
            className="flex items-center gap-2"
            labelClassName="text-sm text-fg dark:text-fg-dark"
            label={t('importModal.agentDependencies.importAllAgentTools')}
          />
          <ul className="ml-6 text-xs text-fg-secondary dark:text-fg-secondary-dark space-y-0.5">
            {preview.agent_tools.map((t) => (
              <li key={t.component_name}>
                {t.component_name}
              </li>
            ))}
          </ul>
        </DepCard>
      )}
    </div>
  );
}

export default AgentStepDeps;
