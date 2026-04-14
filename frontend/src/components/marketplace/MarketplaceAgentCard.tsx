import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Bot, BookOpen } from 'lucide-react';
import { Badge } from '../ui/Badge';
import { StarRating } from './StarRating';
import { apiService } from '../../services/api';
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
 * Shows icon, display name, short description, category, knowledge base badge, tags,
 * rating stats, conversation count, and a "Start Chat" quick-start button.
 */
export function MarketplaceAgentCard({ agent, onClick }: MarketplaceAgentCardProps) {
  const navigate = useNavigate();
  const [starting, setStarting] = useState(false);

  const handleStartChat = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (starting) return;
    setStarting(true);
    try {
      const conv = await apiService.createMarketplaceConversation(agent.agent_id);
      navigate(`/marketplace/chat/${conv.conversation_id ?? conv.id}`);
    } finally {
      setStarting(false);
    }
  };

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
            <Bot className="w-5 h-5 text-blue-400" aria-hidden="true" />
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

      {/* Stats row: rating + conversation count + published date */}
      <div className="flex items-center gap-3 mb-3 text-xs text-gray-500">
        <div className="flex items-center gap-1">
          <StarRating value={agent.rating_avg ? Math.round(agent.rating_avg) : null} size="sm" />
          {agent.rating_avg === null ? (
            <span className="text-gray-400">No ratings</span>
          ) : (
            <span>{agent.rating_avg.toFixed(1)} ({agent.rating_count})</span>
          )}
        </div>
        {agent.conversation_count > 0 && (
          <span>{agent.conversation_count.toLocaleString()} chats</span>
        )}
        <span className="ml-auto text-gray-400">
          {agent.published_at
            ? new Date(agent.published_at).toLocaleDateString('en-CA')
            : '—'}
        </span>
      </div>

      {/* Bottom row: category + knowledge badge + tags + start chat button */}
      <div className="flex flex-wrap items-center gap-1.5 mt-auto">
        {agent.category && (
          <Badge
            label={agent.category}
            variant={CATEGORY_VARIANT[agent.category] ?? 'default'}
          />
        )}
        {agent.has_knowledge_base && (
          <Badge label="Knowledge" variant="success" icon={<BookOpen className="w-3 h-3" />} />
        )}
        {agent.tags?.slice(0, 3).map((tag) => (
          <Badge key={tag} label={tag} variant="default" />
        ))}

        {/* Spacer */}
        <span className="flex-1" />

        {/* Quick-start button */}
        <button
          type="button"
          onClick={handleStartChat}
          disabled={starting}
          className="ml-auto px-2.5 py-1 text-xs font-medium bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors whitespace-nowrap"
          aria-label={`Start chat with ${agent.display_name}`}
        >
          {starting ? '…' : 'Start Chat'}
        </button>
      </div>
    </button>
  );
}

export default MarketplaceAgentCard;
