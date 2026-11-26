import { useCallback, useEffect, useState } from 'react';
import { apiService, type Agent, type EmbeddingService } from '../../../services/api';
import type { PieceKind } from './agentPorts';

/**
 * One connectable piece shown around the edited agent: an existing app or
 * system resource (AI service, silo, skill, MCP config, middleware, sandbox
 * service, embedding service or another agent usable as a tool).
 */
export interface CanvasPieceAgentInfo {
  /** Raw agent type from the API (`agent`, `ocr_agent`, ...). */
  readonly type: string;
  readonly description?: string;
  /** Name of the agent's AI service, when it has one. */
  readonly modelName?: string;
  readonly toolCount: number;
  readonly requestCount: number;
  /** ISO date of the agent's last use; null when it was never used. */
  readonly lastUsedDate: string | null;
}

export interface CanvasPiece {
  readonly kind: PieceKind;
  readonly id: number;
  readonly name: string;
  readonly lifecycleStatus?: 'active' | 'deprecated' | 'retired';
  readonly isSystem?: boolean;
  /** Agent pieces only: whether the agent is already usable as a tool. */
  readonly isTool?: boolean;
  /** Agent pieces only: read-only details for the inspector. */
  readonly agentInfo?: CanvasPieceAgentInfo;
  /** AI services only: whether the service can analyse video (absent = unknown = no). */
  readonly supportsVideo?: boolean;
}

export interface UseAgentCanvasDataResult {
  readonly agent: Agent | null;
  readonly pieces: CanvasPiece[];
  /** Every agent's `tool_ids`, keyed by agent id - feeds the tool-cycle check. */
  readonly toolEdges: Record<number, number[]>;
  readonly loading: boolean;
  readonly error: string | null;
  readonly refetch: () => Promise<void>;
}

/** Option items the `Agent` type under-declares; read defensively. */
interface ServiceOptionItem {
  readonly service_id: number;
  readonly name: string;
  readonly is_system?: unknown;
  readonly lifecycle_status?: unknown;
  readonly supports_video?: unknown;
}

interface SandboxOptionItem {
  readonly service_id: number;
  readonly name: string;
  readonly lifecycle_status?: unknown;
}

interface SkillOptionItem {
  readonly skill_id: number;
  readonly name: string;
  readonly is_system?: unknown;
}

function optionList<T>(value: unknown): T[] {
  return Array.isArray(value) ? (value as T[]) : [];
}

function lifecycleStatus(value: unknown): CanvasPiece['lifecycleStatus'] {
  return value === 'active' || value === 'deprecated' || value === 'retired' ? value : undefined;
}

/** System services carry an `is_system` flag when present, else a "[System] " name prefix. */
function isSystemService(item: { name: string; is_system?: unknown }): boolean | undefined {
  if (item.is_system === true) return true;
  return item.name.startsWith('[System] ') ? true : undefined;
}

/**
 * Builds the palette/canvas pieces from the agent detail's option lists (the
 * same lists the agent form uses, so system items and lifecycle status ride
 * along), the app's agent list (other agents, excluding the edited one) and
 * the app's embedding services.
 */
function buildPieces(agent: Agent, agents: Agent[], embeddings: EmbeddingService[], editedAgentId: number): CanvasPiece[] {
  const pieces: CanvasPiece[] = [];
  for (const service of optionList<ServiceOptionItem>(agent.ai_services)) {
    pieces.push({
      kind: 'ai_service',
      id: service.service_id,
      name: service.name,
      lifecycleStatus: lifecycleStatus(service.lifecycle_status),
      isSystem: isSystemService(service),
      supportsVideo: service.supports_video === true,
    });
  }
  for (const service of optionList<SandboxOptionItem>(agent.sandbox_services)) {
    pieces.push({
      kind: 'sandbox',
      id: service.service_id,
      name: service.name,
      lifecycleStatus: lifecycleStatus(service.lifecycle_status),
      isSystem: isSystemService(service),
    });
  }
  for (const silo of optionList<{ silo_id: number; name: string }>(agent.silos)) {
    pieces.push({ kind: 'silo', id: silo.silo_id, name: silo.name });
  }
  for (const parser of optionList<{ parser_id: number; name: string }>(agent.output_parsers)) {
    pieces.push({ kind: 'parser', id: parser.parser_id, name: parser.name });
  }
  for (const config of optionList<{ config_id: number; name: string }>(agent.mcp_configs)) {
    pieces.push({ kind: 'mcp', id: config.config_id, name: config.name });
  }
  for (const skill of optionList<SkillOptionItem>(agent.skills)) {
    pieces.push({ kind: 'skill', id: skill.skill_id, name: skill.name, isSystem: skill.is_system === true ? true : undefined });
  }
  for (const middleware of optionList<{ middleware_id: number; name: string }>(agent.middlewares)) {
    pieces.push({ kind: 'middleware', id: middleware.middleware_id, name: middleware.name });
  }
  for (const other of agents) {
    if (other.agent_id === editedAgentId) continue;
    pieces.push({
      kind: 'agent',
      id: other.agent_id,
      name: other.name,
      isTool: other.is_tool === true,
      agentInfo: {
        type: other.type,
        description: other.description,
        modelName: other.ai_service?.name,
        toolCount: other.tool_ids?.length ?? 0,
        requestCount: other.request_count,
        lastUsedDate: other.last_used_date,
      },
    });
  }
  for (const embedding of embeddings) {
    pieces.push({
      kind: 'embedding',
      id: embedding.service_id,
      name: embedding.name,
      lifecycleStatus: lifecycleStatus(embedding.lifecycle_status),
      isSystem: embedding.is_system === true ? true : undefined,
    });
  }
  return pieces;
}

function buildToolEdges(agents: Agent[]): Record<number, number[]> {
  const edges: Record<number, number[]> = {};
  for (const agent of agents) edges[agent.agent_id] = agent.tool_ids ?? [];
  return edges;
}

/**
 * Read-only data layer for the per-agent visual canvas: the edited agent
 * (detail payload, which also carries the option lists the palette needs)
 * plus the pieces it may connect to. Deliberately framework-neutral.
 */
export function useAgentCanvasData(appId: number, agentId: number): UseAgentCanvasDataResult {
  const [data, setData] = useState<{ agent: Agent | null; pieces: CanvasPiece[]; toolEdges: Record<number, number[]> }>({
    agent: null,
    pieces: [],
    toolEdges: {},
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [agent, agents, embeddings] = await Promise.all([
        apiService.getAgent(appId, agentId),
        apiService.getAgents(appId),
        apiService.getEmbeddingServices(appId),
      ]);
      setData({
        agent,
        pieces: buildPieces(agent, agents, embeddings, agentId),
        toolEdges: buildToolEdges(agents),
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load agent canvas');
    } finally {
      setLoading(false);
    }
  }, [appId, agentId]);

  useEffect(() => {
    void fetchAll();
  }, [fetchAll]);

  return { agent: data.agent, pieces: data.pieces, toolEdges: data.toolEdges, loading, error, refetch: fetchAll };
}
