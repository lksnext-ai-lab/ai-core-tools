import { useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import Alert from '../../ui/Alert';
import ExpansionDetails from '../../ui/ExpansionDetails';
import { FormField } from '../../ui/FormField';
import type {
  AppImportPreview,
  DependencyInfo,
} from '../../../types/import';
import {
  COMPONENT_TYPE_ICONS,
} from '../../../types/import';
import {
  buildDependencyGraph,
  getDeselectionImpact,
  getSelectionImpact,
} from '../../../utils/dependencyGraph';

interface Props {
  preview: AppImportPreview;
  selection: Record<string, boolean>;
  onSelectionChange: (
    selection: Record<string, boolean>
  ) => void;
}

interface CategoryConfig {
  type: string;
  label: string;
  icon: string;
  items: Array<{
    key: string;
    name: string;
    needsApiKey: boolean;
    deps: DependencyInfo[];
  }>;
}

function makeKey(type: string, name: string): string {
  return `${type}:${name}`;
}

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

function AppStepSelect({
  preview,
  selection,
  onSelectionChange,
}: Readonly<Props>) {
  const { t } = useTranslation('common');
  const graph = buildDependencyGraph(preview.dependencies);

  const categories: CategoryConfig[] = [
    {
      type: 'ai_service',
      label: t('importModal.appUpload.components.aiServices', { count: preview.ai_services.length }),
      icon: COMPONENT_TYPE_ICONS.ai_service,
      items: preview.ai_services.map((c) => ({
        key: makeKey('ai_service', c.component_name),
        name: c.component_name,
        needsApiKey: c.needs_api_key,
        deps: preview.dependencies.filter(
          (d) =>
            d.source_type === 'ai_service' &&
            d.source_name === c.component_name
        ),
      })),
    },
    {
      type: 'embedding_service',
      label: t('importModal.appUpload.components.embeddingServices', { count: preview.embedding_services.length }),
      icon: COMPONENT_TYPE_ICONS.embedding_service,
      items: preview.embedding_services.map((c) => ({
        key: makeKey(
          'embedding_service',
          c.component_name
        ),
        name: c.component_name,
        needsApiKey: c.needs_api_key,
        deps: preview.dependencies.filter(
          (d) =>
            d.source_type === 'embedding_service' &&
            d.source_name === c.component_name
        ),
      })),
    },
    {
      type: 'output_parser',
      label: t('importModal.appUpload.components.outputParsers', { count: preview.output_parsers.length }),
      icon: COMPONENT_TYPE_ICONS.output_parser,
      items: preview.output_parsers.map((c) => ({
        key: makeKey('output_parser', c.component_name),
        name: c.component_name,
        needsApiKey: false,
        deps: [],
      })),
    },
    {
      type: 'mcp_config',
      label: t('importModal.appUpload.components.mcpConfigs', { count: preview.mcp_configs.length }),
      icon: COMPONENT_TYPE_ICONS.mcp_config,
      items: preview.mcp_configs.map((c) => ({
        key: makeKey('mcp_config', c.component_name),
        name: c.component_name,
        needsApiKey: false,
        deps: [],
      })),
    },
    {
      type: 'silo',
      label: t('importModal.appUpload.components.silos', { count: preview.silos.length }),
      icon: COMPONENT_TYPE_ICONS.silo,
      items: preview.silos.map((c) => ({
        key: makeKey('silo', c.component_name),
        name: c.component_name,
        needsApiKey: false,
        deps: preview.dependencies.filter(
          (d) =>
            d.source_type === 'silo' &&
            d.source_name === c.component_name
        ),
      })),
    },
    {
      type: 'repository',
      label: t('importModal.appUpload.components.repositories', { count: preview.repositories.length }),
      icon: COMPONENT_TYPE_ICONS.repository,
      items: preview.repositories.map((c) => ({
        key: makeKey('repository', c.component_name),
        name: c.component_name,
        needsApiKey: false,
        deps: preview.dependencies.filter(
          (d) =>
            d.source_type === 'repository' &&
            d.source_name === c.component_name
        ),
      })),
    },
    {
      type: 'domain',
      label: t('importModal.appUpload.components.domains', { count: preview.domains.length }),
      icon: COMPONENT_TYPE_ICONS.domain,
      items: preview.domains.map((c) => ({
        key: makeKey('domain', c.component_name),
        name: c.component_name,
        needsApiKey: false,
        deps: preview.dependencies.filter(
          (d) =>
            d.source_type === 'domain' &&
            d.source_name === c.component_name
        ),
      })),
    },
    {
      type: 'agent',
      label: t('importModal.appUpload.components.agents', { count: preview.agents.length }),
      icon: COMPONENT_TYPE_ICONS.agent,
      items: preview.agents.map((c) => ({
        key: makeKey('agent', c.component_name),
        name: c.component_name,
        needsApiKey: false,
        deps: preview.dependencies.filter(
          (d) =>
            d.source_type === 'agent' &&
            d.source_name === c.component_name
        ),
      })),
    },
  ].filter((cat) => cat.items.length > 0);

  const toggleItem = useCallback(
    (key: string, selected: boolean) => {
      const updated = { ...selection };

if (selected) {
      // Selecting: auto-select mandatory deps
      const impact = getSelectionImpact(
        graph,
        key,
        selection
      );
      updated[key] = true;
      for (const k of impact.autoSelect) {
        updated[k] = true;
      }
    } else {
      // Deselecting: cascade mandatory dependents
      const impact = getDeselectionImpact(
        graph,
        key,
        selection
      );
      updated[key] = false;
      for (const k of impact.autoDeselect) {
        updated[k] = false;
        }
      }

      onSelectionChange(updated);
    },
    [selection, graph, onSelectionChange]
  );

  const toggleCategory = useCallback(
    (cat: CategoryConfig, selectAll: boolean) => {
      const updated = { ...selection };
      for (const item of cat.items) {
        if (selectAll) {
          updated[item.key] = true;
          const impact = getSelectionImpact(
            graph,
            item.key,
            updated
          );
          for (const k of impact.autoSelect) {
            updated[k] = true;
          }
        } else {
          updated[item.key] = false;
          const impact = getDeselectionImpact(
            graph,
            item.key,
            updated
          );
          for (const k of impact.autoDeselect) {
            updated[k] = false;
          }
        }
      }
      onSelectionChange(updated);
    },
    [selection, graph, onSelectionChange]
  );

  const selectedCount = Object.values(selection).filter(
    Boolean
  ).length;
  const totalCount = Object.keys(selection).length;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-gray-600">
          {t('importModal.appSelect.description')}
        </p>
        <span className="text-xs text-gray-500">
          {t('importModal.appSelect.selectedCount', {
            selected: selectedCount,
            total: totalCount,
          })}
        </span>
      </div>

      {categories.map((cat) => {
        const catSelectedCount = cat.items.filter(
          (i) => selection[i.key]
        ).length;
        const allSelected =
          catSelectedCount === cat.items.length;

        return (
          <ExpansionDetails
            key={cat.type}
            header={(
              <span className="flex items-center space-x-2">
                <span aria-hidden="true">{cat.icon}</span>
                <span>{cat.label}</span>
              </span>
            )}
            headerStart={(
              <FormField
                id={`select-all-${cat.type}`}
                type="checkbox"
                checked={allSelected}
                ariaLabel={t('importModal.appSelect.selectAllCategory', {
                  category: cat.label,
                })}
                onChange={(e) => toggleCategory(cat, e.target.checked)}
              />
            )}
            headerExtra={(
              <span className="text-xs text-gray-500">
                {catSelectedCount}/{cat.items.length}
              </span>
            )}
          >
            <div className="divide-y divide-line dark:divide-line-dark">
              {cat.items.map((item) => {
                const depLabels = item.deps.map((d) => {
                  const translationKey = COMPONENT_TYPE_TRANSLATION_KEYS[d.depends_on_type];
                  const label = translationKey
                    ? t(`importModal.appUpload.components.${translationKey}`, { count: 1 })
                    : t('importModal.unknown');
                  return `${label}: ${d.depends_on_name}`;
                });
                const itemHelpText = [
                  item.needsApiKey ? t('importModal.appSelect.apiKeyRequired') : undefined,
                  depLabels.length > 0
                    ? t('importModal.appSelect.dependencies', {
                      count: depLabels.length,
                      items: depLabels.join(', '),
                    })
                    : undefined,
                ].filter(Boolean).join(' · ');

                return (
                  <div
                    key={item.key}
                    className="px-4 py-2 flex items-center justify-between"
                  >
                    <FormField
                      id={`component-${item.key}`}
                      type="checkbox"
                      label={item.name}
                      checked={!!selection[item.key]}
                      onChange={(e) => toggleItem(item.key, e.target.checked)}
                      helpText={itemHelpText || undefined}
                      className="grid min-w-0 flex-1 grid-cols-[auto_minmax(0,1fr)] items-center gap-x-2 [&>p]:col-span-2"
                      labelClassName="mb-0 min-w-0 truncate text-sm font-medium text-fg dark:text-fg-dark"
                    />
                  </div>
                );
              })}
            </div>
          </ExpansionDetails>
        );
      })}

      {selectedCount === 0 && (
        <Alert
          type="warning"
          message={t('importModal.appSelect.noneSelected')}
        />
      )}
    </div>
  );
}

export default AppStepSelect;
