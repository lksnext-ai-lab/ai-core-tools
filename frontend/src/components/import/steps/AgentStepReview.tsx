import Alert from '../../ui/Alert';
import type {
  AgentImportPreview,
  ConflictMode,
} from '../../../types/import';
import { COMPONENT_TYPE_ICONS } from '../../../types/import';
import type { ServiceOptionLike } from '../../../utils/serviceLifecycle';
import Table, { type TableColumn } from '../../ui/Table';
import { Badge, type BadgeVariant } from '../../ui/Badge';
import { useTranslation } from 'react-i18next';

interface Props {
  preview: AgentImportPreview;
  conflictMode: ConflictMode;
  newName: string;
  useExistingAIService: boolean;
  selectedAIServiceId: number | null;
  availableAIServices: readonly ServiceOptionLike[];
  importBundledSilo: boolean;
  importBundledOutputParser: boolean;
  importBundledMCPConfigs: boolean;
  importBundledAgentTools: boolean;
}

type ReviewAction =
  | 'create'
  | 'update'
  | 'createRenamed'
  | 'fail'
  | 'useExisting'
  | 'importNew'
  | 'import'
  | 'skip';

type ReviewRow = {
  icon: string;
  type: string;
  name: string;
  action: ReviewAction;
  actionName?: string;
};

const ACTION_BADGE_VARIANTS: Record<ReviewAction, BadgeVariant> = {
  create: 'success',
  update: 'success',
  createRenamed: 'success',
  fail: 'error',
  useExisting: 'success',
  importNew: 'success',
  import: 'success',
  skip: 'default',
};

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
}: Readonly<Props>) {
  const { t } = useTranslation('common');

  const agentAction = () => {
    if (!preview.agent.has_conflict) return 'create';
    if (conflictMode === 'override') return 'update';
    if (conflictMode === 'rename') return 'createRenamed';
    return 'fail';
  };

  const agentDisplayName =
    conflictMode === 'rename' && newName
      ? newName
      : preview.agent.component_name;

  const aiServiceAction = (): Pick<ReviewRow, 'action' | 'actionName'> => {
    if (useExistingAIService || !preview.ai_service) {
      const svc = availableAIServices.find(
        (s) => s.service_id === selectedAIServiceId
      );
      return { action: 'useExisting', actionName: svc?.name };
    }
    return { action: 'importNew' };
  };

  const rows: ReviewRow[] = [
    {
      icon: COMPONENT_TYPE_ICONS.agent,
      type: t('importModal.agentUpload.components.agent'),
      name: agentDisplayName,
      action: agentAction(),
    },
    {
      icon: COMPONENT_TYPE_ICONS.ai_service,
      type: t('importModal.agentUpload.components.aiService'),
      name: preview.ai_service?.component_name || '—',
      ...aiServiceAction(),
    },
    preview.silo
      ? {
          icon: COMPONENT_TYPE_ICONS.silo,
          type: t('importModal.agentUpload.components.silo'),
          name: preview.silo.component_name,
          action: importBundledSilo ? 'import' : 'skip',
        }
      : null,
    preview.output_parser
      ? {
          icon: COMPONENT_TYPE_ICONS.output_parser,
          type: t('importModal.agentUpload.components.outputParser'),
          name: preview.output_parser.component_name,
          action: importBundledOutputParser ? 'import' : 'skip',
        }
      : null,
    preview.mcp_configs.length > 0
      ? {
          icon: COMPONENT_TYPE_ICONS.mcp_config,
          type: t('importModal.agentUpload.components.mcpConfigs', {
            count: preview.mcp_configs.length,
          }),
          name: t('importModal.agentReview.counts.mcpConfigs', {
            count: preview.mcp_configs.length,
          }),
          action: importBundledMCPConfigs ? 'import' : 'skip',
        }
      : null,
    preview.agent_tools.length > 0
      ? {
          icon: COMPONENT_TYPE_ICONS.agent,
          type: t('importModal.agentUpload.components.agentTools', {
            count: preview.agent_tools.length,
          }),
          name: t('importModal.agentReview.counts.agentTools', {
            count: preview.agent_tools.length,
          }),
          action: importBundledAgentTools ? 'import' : 'skip',
        }
      : null,
  ].filter((row): row is ReviewRow => row !== null);

  const actionLabel = (row: ReviewRow) =>
    row.action === 'useExisting'
      ? t('importModal.agentReview.actions.useExisting', {
          name: row.actionName ?? t('importModal.agentReview.none'),
        })
      : t(`importModal.agentReview.actions.${row.action}`);

  const columns: TableColumn<ReviewRow>[] = [
    {
      header: t('importModal.agentReview.columns.component'),
      render: (row) => (
        <>
          <span className="mr-1">{row.icon}</span>
          {row.type}
        </>
      ),
    },
    {
      header: t('importModal.agentReview.columns.name'),
      accessor: 'name',
      className: 'px-6 py-4 text-sm text-fg dark:text-fg-dark',
    },
    {
      header: t('importModal.agentReview.columns.action'),
      render: (row) => {
        return (
          <Badge
            label={actionLabel(row)}
            variant={ACTION_BADGE_VARIANTS[row.action]}
          />
        );
      },
    },
  ];

  return (
    <div className="space-y-4">
      <h4 className="font-display text-[17px] font-medium leading-8 text-fg dark:text-fg-dark">
        {t('importModal.result.summary')}
      </h4>

      <Table
        columns={columns}
        data={rows}
        keyExtractor={(row) => row.type}
      />

      {(!useExistingAIService && preview.ai_service) && (
        <Alert
          type="info"
          message={t('importModal.agentReview.apiKeysWarning')}
        />
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

export default AgentStepReview;
