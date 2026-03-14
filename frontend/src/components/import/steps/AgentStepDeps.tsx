import Alert from '../../ui/Alert';
import type { AgentImportPreview } from '../../../types/import';
import { COMPONENT_TYPE_ICONS } from '../../../types/import';

interface Props {
  preview: AgentImportPreview;
  useExistingAIService: boolean;
  onUseExistingAIServiceChange: (val: boolean) => void;
  selectedAIServiceId: number | null;
  onSelectedAIServiceIdChange: (id: number | null) => void;
  availableAIServices: Array<{ id: number; name: string }>;
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
  children,
}: Readonly<{
  icon: string;
  title: string;
  badge: 'Required' | 'Optional';
  children: React.ReactNode;
}>) {
  return (
    <div className="bg-gray-50 border border-gray-200 rounded-lg p-4 space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-2">
          <span>{icon}</span>
          <span className="font-medium text-gray-900">
            {title}
          </span>
        </div>
        <span
          className={`text-xs px-2 py-0.5 rounded-full font-medium ${
            badge === 'Required'
              ? 'bg-red-100 text-red-700'
              : 'bg-gray-200 text-gray-600'
          }`}
        >
          {badge}
        </span>
      </div>
      {children}
    </div>
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
  return (
    <div className="space-y-4">
      <p className="text-sm text-gray-600">
        Configure how dependencies are resolved for this agent.
      </p>

      {/* AI Service - Mandatory */}
      <DepCard
        icon={COMPONENT_TYPE_ICONS.ai_service}
        title="AI Service"
        badge="Required"
      >
        {preview.ai_service ? (
          <>
            <div className="space-y-2">
              <label className="flex items-center space-x-2">
                <input
                  type="radio"
                  name="ai_service_source"
                  checked={!useExistingAIService}
                  onChange={() =>
                    onUseExistingAIServiceChange(false)
                  }
                  className="text-blue-600"
                />
                <span className="text-sm text-gray-700">
                  Import bundled:{' '}
                  <strong>
                    {preview.ai_service.component_name}
                  </strong>
                  {preview.ai_service.provider && (
                    <span className="text-gray-500 ml-1">
                      ({preview.ai_service.provider})
                    </span>
                  )}
                </span>
              </label>
              <label className="flex items-center space-x-2">
                <input
                  type="radio"
                  name="ai_service_source"
                  checked={useExistingAIService}
                  onChange={() =>
                    onUseExistingAIServiceChange(true)
                  }
                  className="text-blue-600"
                />
                <span className="text-sm text-gray-700">
                  Use existing AI service
                </span>
              </label>
            </div>
            {useExistingAIService && (
              <select
                value={selectedAIServiceId ?? ''}
                onChange={(e) =>
                  onSelectedAIServiceIdChange(
                    e.target.value
                      ? Number(e.target.value)
                      : null
                  )
                }
                className="w-full mt-2 border border-gray-300 rounded-lg px-3 py-2 text-sm"
              >
                <option value="">
                  -- Select AI Service --
                </option>
                {availableAIServices.map((svc) => (
                  <option key={svc.id} value={svc.id}>
                    {svc.name}
                  </option>
                ))}
              </select>
            )}
            {!useExistingAIService && (
              <p className="text-xs text-amber-700 bg-amber-50 rounded p-2">
                API key will need to be configured after import.
              </p>
            )}
          </>
        ) : (
          <>
            <Alert
              type="warning"
              message={`AI service "${preview.agent.component_name}" requires is not bundled. Select an existing one.`}
            />
            <select
              value={selectedAIServiceId ?? ''}
              onChange={(e) =>
                onSelectedAIServiceIdChange(
                  e.target.value
                    ? Number(e.target.value)
                    : null
                )
              }
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
            >
              <option value="">
                -- Select AI Service --
              </option>
              {availableAIServices.map((svc) => (
                <option key={svc.id} value={svc.id}>
                  {svc.name}
                </option>
              ))}
            </select>
          </>
        )}
      </DepCard>

      {/* Silo - Optional */}
      {preview.silo && (
        <DepCard
          icon={COMPONENT_TYPE_ICONS.silo}
          title="Silo (Knowledge Base)"
          badge="Optional"
        >
          <label className="flex items-center space-x-2">
            <input
              type="checkbox"
              checked={importBundledSilo}
              onChange={(e) =>
                onImportBundledSiloChange(e.target.checked)
              }
              className="rounded border-gray-300"
            />
            <span className="text-sm text-gray-700">
              Import: {preview.silo.component_name}
            </span>
          </label>
          {preview.silo_embedding_service && importBundledSilo && (
            <p className="text-xs text-gray-500 ml-6">
              Includes embedding service:{' '}
              {preview.silo_embedding_service.component_name}
            </p>
          )}
          {preview.silo_output_parser && importBundledSilo && (
            <p className="text-xs text-gray-500 ml-6">
              Includes output parser:{' '}
              {preview.silo_output_parser.component_name}
            </p>
          )}
        </DepCard>
      )}

      {/* Output Parser - Optional */}
      {preview.output_parser && (
        <DepCard
          icon={COMPONENT_TYPE_ICONS.output_parser}
          title="Output Parser"
          badge="Optional"
        >
          <label className="flex items-center space-x-2">
            <input
              type="checkbox"
              checked={importBundledOutputParser}
              onChange={(e) =>
                onImportBundledOutputParserChange(
                  e.target.checked
                )
              }
              className="rounded border-gray-300"
            />
            <span className="text-sm text-gray-700">
              Import:{' '}
              {preview.output_parser.component_name}
            </span>
          </label>
        </DepCard>
      )}

      {/* MCP Configs - Optional */}
      {preview.mcp_configs.length > 0 && (
        <DepCard
          icon={COMPONENT_TYPE_ICONS.mcp_config}
          title={`MCP Configs (${preview.mcp_configs.length})`}
          badge="Optional"
        >
          <label className="flex items-center space-x-2">
            <input
              type="checkbox"
              checked={importBundledMCPConfigs}
              onChange={(e) =>
                onImportBundledMCPConfigsChange(
                  e.target.checked
                )
              }
              className="rounded border-gray-300"
            />
            <span className="text-sm text-gray-700">
              Import all MCP configs
            </span>
          </label>
          <ul className="ml-6 text-xs text-gray-500 space-y-0.5">
            {preview.mcp_configs.map((m) => (
              <li key={m.component_name}>
                {m.component_name}
              </li>
            ))}
          </ul>
        </DepCard>
      )}

      {/* Agent Tools - Optional */}
      {preview.agent_tools.length > 0 && (
        <DepCard
          icon={COMPONENT_TYPE_ICONS.agent}
          title={`Agent Tools (${preview.agent_tools.length})`}
          badge="Optional"
        >
          <label className="flex items-center space-x-2">
            <input
              type="checkbox"
              checked={importBundledAgentTools}
              onChange={(e) =>
                onImportBundledAgentToolsChange(
                  e.target.checked
                )
              }
              className="rounded border-gray-300"
            />
            <span className="text-sm text-gray-700">
              Import all agent tools
            </span>
          </label>
          <ul className="ml-6 text-xs text-gray-500 space-y-0.5">
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
