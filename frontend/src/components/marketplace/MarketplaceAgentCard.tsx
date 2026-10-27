import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Bot, BookOpen } from 'lucide-react';
import { Badge } from '../ui/Badge';
import { ButtonApp } from '../ui/ButtonApp';
import { StarRating } from './StarRating';
import { ButtonCard } from '../ui/ButtonCard';
import { apiService } from '../../services/api';
import { useApiMutation } from '../../hooks/useApiMutation';
import { errorMessage } from '../../constants/messages';
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
 */
export function MarketplaceAgentCard({ agent, onClick }: MarketplaceAgentCardProps) {
  const navigate = useNavigate();
  const mutate = useApiMutation();
  const [starting, setStarting] = useState(false);

  const handleStartChat = async () => {
    if (starting) return;
    setStarting(true);
    const conv = await mutate(
      () => apiService.createMarketplaceConversation(agent.agent_id),
      {
        loading: 'Starting conversation…',
        success: 'Conversation started',
        error: (err) => errorMessage(err, 'Failed to start conversation'),
      },
    );
    setStarting(false);
    if (!conv) return;
    navigate(`/marketplace/chat/${conv.conversation_id ?? conv.id}`);
  };

  return (
    <ButtonCard
      onClick={() => onClick(agent.agent_id)}
      ariaLabel={`Open ${agent.display_name}`}
    >
      <div className="mb-3 flex min-w-0 items-center gap-3">
        <div className="flex h-[34px] w-[34px] shrink-0 items-center justify-center overflow-hidden rounded-md border-[0.8px] border-[#FF682C] text-sm font-medium">
          <Bot className="w-5 h-5 text-fg dark:text-fg-dark" aria-hidden="true" />
        </div>
        <div className="min-w-0 text-[18px] leading-tight">
          <span className="block text-ink dark:text-ink-dark">{agent.display_name}</span>
          <span className="block text-[12.5px] text-fg-secondary dark:text-fg-secondary-dark">
            {agent.app_name} • {agent.published_at
              ? new Date(agent.published_at).toLocaleDateString('en-CA')
              : '—'}
          </span>
        </div>
      </div>
      <p className="mb-4 whitespace-pre-line text-[13.5px] leading-[1.45] text-fg-secondary dark:text-fg-secondary-dark">
        {agent.short_description || 'No description provided.'}
      </p>
      <div className="mb-4 flex flex-wrap gap-2">
        {agent.category && (
          <Badge label={agent.category} variant={CATEGORY_VARIANT[agent.category] ?? 'default'} />
        )}
        {agent.has_knowledge_base && (
          <Badge label="Knowledge" variant="success" icon={<BookOpen className="w-3 h-3" />} />
        )}
        {agent.tags?.slice(0, 3).map((tag) => (
          <Badge key={`tag-${tag}`} label={tag} variant="default" />
        ))}
      </div>
      <div className="pointer-events-none relative z-0 mt-auto border-t border-[#e0ddd6] dark:border-line-dark">
        <div className="flex items-center gap-3 pt-3 text-xs text-fg-tertiary dark:text-fg-tertiary-dark">
          <div className="flex min-w-0 flex-1 flex-wrap items-center gap-x-3 gap-y-1">
            <div className="flex items-center gap-1">
              <StarRating value={agent.rating_avg ? Math.round(agent.rating_avg) : null} size="sm" />
              {agent.rating_avg === null ? (
                <span className="text-fg-tertiary dark:text-fg-tertiary-dark">No ratings</span>
              ) : (
                <span>{agent.rating_avg.toFixed(1)} ({agent.rating_count})</span>
              )}
            </div>
            {agent.conversation_count > 0 && (
              <span>{agent.conversation_count.toLocaleString()} chats</span>
            )}
          </div>
          <ButtonApp
            label={starting ? '…' : 'Start Chat'}
            variant="primary"
            size="compact"
            type="button"
            onClick={() => void handleStartChat()}
            disabled={starting}
            className="pointer-events-auto relative z-10 shrink-0"
          />
        </div>
      </div>
    </ButtonCard>
  );
}