import React from 'react';
import { Badge } from '../ui/Badge';
import type { MarketplaceAgentCard as MarketplaceAgentCardType } from '../../types/marketplace';

interface MarketplaceAgentCardProps {
  readonly agent: MarketplaceAgentCardType;
  readonly onClick: (agentId: number) => void;
}

/** Category → badge variant mapping */
const CATEGORY_VARIANT: Record<string, 'info' | 'success' | 'warning' | 'error' | 'primary' | 'secondary' | 'default'> = {
  Productivity: 'info',
  Research: 'primary',
  Writing: 'secondary',
  Code: 'success',
  'Data Analysis': 'warning',
  'Customer Support': 'error',
  Education: 'info',
  Other: 'default',
};

/**
 * Card component for displaying a published agent in the marketplace catalog grid.
 * Shows icon, display name, short description, category, knowledge base badge, and tags.
 */
export function MarketplaceAgentCard({ agent, onClick }: MarketplaceAgentCardProps) {
  return (
    <button
      type="button"
      onClick={() => onClick(agent.agent_id)}
      className="bg-white rounded-lg shadow-md border p-5 text-left transition-all duration-200 hover:shadow-lg hover:border-blue-300 cursor-pointer flex flex-col h-full w-full"
    >
      {/* Top section: icon + name + publisher */}
      <div className="flex items-start gap-3 mb-3">
        <div className="flex-shrink-0 w-12 h-12 rounded-lg bg-blue-50 flex items-center justify-center overflow-hidden">
          {agent.icon_url ? (
            <img
              src={agent.icon_url}
              alt={agent.display_name}
              className="w-full h-full object-cover rounded-lg"
            />
          ) : (
            <span className="text-2xl" aria-hidden="true">🤖</span>
          )}
        </div>
        <div className="min-w-0 flex-1">
          <h3 className="text-sm font-semibold text-gray-900 truncate">
            {agent.display_name}
          </h3>
          <p className="text-xs text-gray-500 truncate">{agent.app_name}</p>
        </div>
      </div>

      {/* Middle: short description */}
      <p className="text-sm text-gray-600 line-clamp-3 mb-3 flex-1">
        {agent.short_description || 'No description provided.'}
      </p>

      {/* Bottom row: category + knowledge badge + tags */}
      <div className="flex flex-wrap items-center gap-1.5 mt-auto">
        {agent.category && (
          <Badge
            label={agent.category}
            variant={CATEGORY_VARIANT[agent.category] ?? 'default'}
          />
        )}
        {agent.has_knowledge_base && (
          <Badge label="Knowledge" variant="success" icon="📚" />
        )}
        {agent.tags?.slice(0, 3).map((tag) => (
          <Badge key={tag} label={tag} variant="default" />
        ))}
      </div>
    </button>
  );
}

export default MarketplaceAgentCard;
