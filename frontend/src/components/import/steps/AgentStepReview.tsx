import Alert from '../../ui/Alert';
import type {
  AgentImportPreview,
  ConflictMode,
} from '../../../types/import';
import { COMPONENT_TYPE_ICONS } from '../../../types/import';

interface Props {
  preview: AgentImportPreview;
  conflictMode: ConflictMode;
  newName: string;
  useExistingAIService: boolean;
  selectedAIServiceId: number | null;
  availableAIServices: Array<{ id: number; name: string }>;
  importBundledSilo: boolean;
  importBundledOutputParser: boolean;
  importBundledMCPConfigs: boolean;
  importBundledAgentTools: boolean;
}

function AgentStepReview({
  preview,
  conflictMode,
  newName,
  useExistingAIService,
  selectedAIServiceId,
  availableAIServices,
  importBundledSilo,
  importBundledOutputParser,
  importBundledMCPConfigs,
  importBundledAgentTools,
}: Props) {
  const agentAction = () => {
    if (!preview.agent.has_conflict) return 'Create';
    if (conflictMode === 'override') return 'Update';
    if (conflictMode === 'rename') return 'Create (renamed)';
    return 'Fail';
  };

  const agentDisplayName =
    conflictMode === 'rename' && newName
      ? newName
      : preview.agent.component_name;

  const aiServiceAction = () => {
    if (useExistingAIService || !preview.ai_service) {
      const svc = availableAIServices.find(
        (s) => s.id === selectedAIServiceId
      );
      return `Use existing: ${svc?.name || 'None'}`;
    }
    return 'Import new';
  };

  const rows: Array<{
    icon: string;
    type: string;
    name: string;
    action: string;
  }> = [];

  rows.push({
    icon: COMPONENT_TYPE_ICONS.agent,
    type: 'Agent',
    name: agentDisplayName,
    action: agentAction(),
  });

  rows.push({
    icon: COMPONENT_TYPE_ICONS.ai_service,
    type: 'AI Service',
    name: preview.ai_service?.component_name || '—',
    action: aiServiceAction(),
  });

  if (preview.silo) {
    rows.push({
      icon: COMPONENT_TYPE_ICONS.silo,
      type: 'Silo',
      name: preview.silo.component_name,
      action: importBundledSilo ? 'Import' : 'Skip',
    });
  }

  if (preview.output_parser) {
    rows.push({
      icon: COMPONENT_TYPE_ICONS.output_parser,
      type: 'Output Parser',
      name: preview.output_parser.component_name,
      action: importBundledOutputParser ? 'Import' : 'Skip',
    });
  }

  if (preview.mcp_configs.length > 0) {
    rows.push({
      icon: COMPONENT_TYPE_ICONS.mcp_config,
      type: 'MCP Configs',
      name: `${preview.mcp_configs.length} config(s)`,
      action: importBundledMCPConfigs ? 'Import' : 'Skip',
    });
  }

  if (preview.agent_tools.length > 0) {
    rows.push({
      icon: COMPONENT_TYPE_ICONS.agent,
      type: 'Agent Tools',
      name: `${preview.agent_tools.length} tool(s)`,
      action: importBundledAgentTools ? 'Import' : 'Skip',
    });
  }

  return (
    <div className="space-y-4">
      <h4 className="text-sm font-medium text-gray-900">
        Import Summary
      </h4>

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
            {rows.map((row) => (
              <tr key={row.type}>
                <td className="px-4 py-2 whitespace-nowrap">
                  <span className="mr-1">{row.icon}</span>
                  {row.type}
                </td>
                <td className="px-4 py-2 font-medium text-gray-900">
                  {row.name}
                </td>
                <td className="px-4 py-2">
                  <span
                    className={`inline-flex px-2 py-0.5 text-xs rounded-full font-medium ${
                      row.action === 'Skip'
                        ? 'bg-gray-100 text-gray-600'
                        : row.action === 'Fail'
                        ? 'bg-red-100 text-red-700'
                        : 'bg-green-100 text-green-700'
                    }`}
                  >
                    {row.action}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {(!useExistingAIService && preview.ai_service) && (
        <Alert
          type="info"
          message="API keys for imported services will need to be configured after import."
        />
      )}

      {preview.global_warnings.length > 0 && (
        <Alert
          type="warning"
          title="Warnings"
          message={
            <ul className="list-disc list-inside space-y-1">
              {preview.global_warnings.map((w, i) => (
                <li key={i}>{w}</li>
              ))}
            </ul>
          }
        />
      )}
    </div>
  );
}

export default AgentStepReview;
