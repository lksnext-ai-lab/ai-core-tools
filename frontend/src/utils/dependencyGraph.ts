import type { DependencyInfo } from '../types/import';

export interface DependencyGraph {
  dependents: Map<string, Array<{ key: string; mandatory: boolean }>>;
  requires: Map<string, Array<{ key: string; mandatory: boolean }>>;
}

function makeKey(type: string, name: string): string {
  return `${type}:${name}`;
}

export function buildDependencyGraph(
  dependencies: DependencyInfo[]
): DependencyGraph {
  const dependents = new Map<
    string,
    Array<{ key: string; mandatory: boolean }>
  >();
  const requires = new Map<
    string,
    Array<{ key: string; mandatory: boolean }>
  >();

  for (const dep of dependencies) {
    const sourceKey = makeKey(dep.source_type, dep.source_name);
    const targetKey = makeKey(
      dep.depends_on_type,
      dep.depends_on_name
    );

    // source requires target
    if (!requires.has(sourceKey)) {
      requires.set(sourceKey, []);
    }
    requires
      .get(sourceKey)!
      .push({ key: targetKey, mandatory: dep.mandatory });

    // target has dependent source
    if (!dependents.has(targetKey)) {
      dependents.set(targetKey, []);
    }
    dependents
      .get(targetKey)!
      .push({ key: sourceKey, mandatory: dep.mandatory });
  }

  return { dependents, requires };
}

export interface DeselectionImpact {
  autoDeselect: string[];
  warnings: string[];
}

export function getDeselectionImpact(
  graph: DependencyGraph,
  componentKey: string,
  currentSelection: Record<string, boolean>
): DeselectionImpact {
  const autoDeselect: string[] = [];
  const warnings: string[] = [];
  const visited = new Set<string>();

  function traverse(key: string) {
    if (visited.has(key)) return;
    visited.add(key);

    const deps = graph.dependents.get(key) || [];
    for (const dep of deps) {
      if (!currentSelection[dep.key]) continue;

      if (dep.mandatory) {
        const [type, name] = dep.key.split(':');
        autoDeselect.push(dep.key);
        warnings.push(
          `${formatLabel(type)} "${name}" requires this component ` +
            `and will also be deselected.`
        );
        traverse(dep.key);
      } else {
        const [type, name] = dep.key.split(':');
        warnings.push(
          `${formatLabel(type)} "${name}" references this component. ` +
            `It will be imported without it.`
        );
      }
    }
  }

  traverse(componentKey);
  return { autoDeselect, warnings };
}

export interface SelectionImpact {
  autoSelect: string[];
  warnings: string[];
}

export function getSelectionImpact(
  graph: DependencyGraph,
  componentKey: string,
  currentSelection: Record<string, boolean>
): SelectionImpact {
  const autoSelect: string[] = [];
  const warnings: string[] = [];

  const reqs = graph.requires.get(componentKey) || [];
  for (const req of reqs) {
    if (currentSelection[req.key]) continue;

    if (req.mandatory) {
      const [type, name] = req.key.split(':');
      autoSelect.push(req.key);
      warnings.push(
        `${formatLabel(type)} "${name}" is required and ` +
          `will also be selected.`
      );
    }
  }

  return { autoSelect, warnings };
}

function formatLabel(type: string): string {
  const labels: Record<string, string> = {
    ai_service: 'AI Service',
    embedding_service: 'Embedding Service',
    output_parser: 'Output Parser',
    mcp_config: 'MCP Config',
    silo: 'Silo',
    repository: 'Repository',
    domain: 'Domain',
    agent: 'Agent',
  };
  return labels[type] || type;
}
