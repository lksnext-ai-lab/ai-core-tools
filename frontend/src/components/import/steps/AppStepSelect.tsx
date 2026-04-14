import { useCallback } from 'react';
import Alert from '../../ui/Alert';
import type {
  AppImportPreview,
  DependencyInfo,
} from '../../../types/import';
import {
  COMPONENT_TYPE_ICONS,
  COMPONENT_TYPE_LABELS,
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

function AppStepSelect({
  preview,
  selection,
  onSelectionChange,
}: Readonly<Props>) {
  const graph = buildDependencyGraph(preview.dependencies);

  const categories: CategoryConfig[] = [
    {
      type: 'ai_service',
      label: 'AI Services',
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
      label: 'Embedding Services',
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
      label: 'Output Parsers',
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
      label: 'MCP Configs',
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
      label: 'Silos',
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
      label: 'Repositories',
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
      label: 'Domains',
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
      label: 'Agents',
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
          Select which components to import.
        </p>
        <span className="text-xs text-gray-500">
          {selectedCount}/{totalCount} selected
        </span>
      </div>

      {categories.map((cat) => {
        const catSelectedCount = cat.items.filter(
          (i) => selection[i.key]
        ).length;
        const allSelected =
          catSelectedCount === cat.items.length;

        return (
          <div
            key={cat.type}
            className="border border-gray-200 rounded-lg overflow-hidden"
          >
            {/* Category header */}
            <div className="bg-gray-50 px-4 py-2 flex items-center justify-between">
              <label className="flex items-center space-x-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={allSelected}
                  onChange={() =>
                    toggleCategory(cat, !allSelected)
                  }
                  className="rounded border-gray-300"
                />
                <span className="mr-1">{cat.icon}</span>
                <span className="text-sm font-medium text-gray-900">
                  {cat.label}
                </span>
              </label>
              <span className="text-xs text-gray-500">
                {catSelectedCount}/{cat.items.length}
              </span>
            </div>

            {/* Items */}
            <div className="divide-y divide-gray-100">
              {cat.items.map((item) => {
                const depLabels = item.deps.map((d) => {
                  const label =
                    COMPONENT_TYPE_LABELS[
                      d.depends_on_type
                    ] || d.depends_on_type;
                  return `${label}: ${d.depends_on_name}`;
                });

                return (
                  <div
                    key={item.key}
                    className="px-4 py-2 flex items-center justify-between"
                  >
                    <label className="flex items-center space-x-2 cursor-pointer flex-1 min-w-0">
                      <input
                        type="checkbox"
                        checked={!!selection[item.key]}
                        onChange={(e) =>
                          toggleItem(
                            item.key,
                            e.target.checked
                          )
                        }
                        className="rounded border-gray-300"
                      />
                      <span className="text-sm text-gray-800 truncate">
                        {item.name}
                      </span>
                    </label>
                    <div className="flex items-center space-x-2 ml-2 flex-shrink-0">
                      {item.needsApiKey && (
                        <span className="text-xs px-2 py-0.5 rounded-full bg-amber-100 text-amber-700 font-medium">
                          Needs API Key
                        </span>
                      )}
                      {depLabels.length > 0 && (
                        <span
                          className="text-xs text-gray-400"
                          title={depLabels.join(', ')}
                        >
                          {depLabels.length} dep
                          {depLabels.length > 1
                            ? 's'
                            : ''}
                        </span>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        );
      })}

      {selectedCount === 0 && (
        <Alert
          type="warning"
          message="No components selected. Select at least one component to import."
        />
      )}
    </div>
  );
}

export default AppStepSelect;
