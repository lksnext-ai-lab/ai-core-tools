import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { ArrowLeft, Bot } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { apiService } from '../services/api';
import { LoadingState } from '../components/ui/LoadingState';
import { ErrorState } from '../components/ui/ErrorState';
import { Badge } from '../components/ui/Badge';
import ButtonApp from '../components/ui/ButtonApp';
import { StarRating } from '../components/marketplace/StarRating';
import { useApiMutation } from '../hooks/useApiMutation';
import { errorMessage } from '../constants/messages';
import type {
  MarketplaceAgentDetail,
  MarketplaceConversation,
} from '../types/marketplace';
import BackgroundImage from '../components/ui/BackgroundImage';
import CardApp from '../components/ui/CardApp';

/** Parses an agent-load error into a user-friendly message. */
function getAgentLoadError(err: unknown): string {
  const msg = err instanceof Error ? err.message : 'Failed to load agent';
  if (msg.includes('404') || msg.includes('not found')) {
    return 'Agent not found or no longer available.';
  }
  return msg;
}

interface RatingSummaryProps {
  readonly ratingAvg: number | null;
  readonly ratingCount: number;
  readonly conversationCount: number;
}

function RatingSummary({ ratingAvg, ratingCount, conversationCount }: RatingSummaryProps) {
  return (
    <div className="flex items-center gap-2 mt-1.5">
      <StarRating value={ratingAvg ? Math.round(ratingAvg) : null} size="md" />
      {ratingAvg === null ? (
        <span className="text-sm text-fg-default dark:text-fg-default-dark">No ratings yet</span>
      ) : (
        <span className="text-sm text-fg-default dark:text-fg-default-dark">
          {ratingAvg.toFixed(1)}{' '}
          <span className="text-fg-default dark:text-fg-default-dark">({ratingCount} rating{ratingCount === 1 ? '' : 's'})</span>
        </span>
      )}
      {conversationCount > 0 && (
        <span className="text-sm text-fg-default dark:text-fg-default-dark">
          · {conversationCount.toLocaleString()} conversations
        </span>
      )}
    </div>
  );
}

/** Category → badge variant mapping (shared with MarketplaceAgentCard) */
const CATEGORY_VARIANT: Record<
  string,
  'info' | 'success' | 'warning' | 'error' | 'primary' | 'secondary' | 'default'
> = {
  Productivity: 'info',
  Research: 'primary',
  Writing: 'secondary',
  Code: 'success',
  'Data Analysis': 'warning',
  'Customer Support': 'error',
  Education: 'info',
  Other: 'default',
};

interface MarketplaceAgentDetailPageProps {
  /** Agent to show. Defaults to the `:agentId` route param. */
  readonly agentId?: number;
  /** `panel` renders a compact single-column layout for the marketplace side panel. */
  readonly variant?: 'page' | 'panel';
}

/**
 * Marketplace agent detail page — full profile view with description,
 * metadata, existing conversations, and "Start Chat" action.
 */
export default function MarketplaceAgentDetailPage({
  agentId: agentIdProp,
  variant = 'page',
}: MarketplaceAgentDetailPageProps = {}) {
  const { agentId } = useParams<{ agentId: string }>();
  const navigate = useNavigate();
  const mutate = useApiMutation();
  const numericId = agentIdProp ?? Number(agentId);
  const isPanel = variant === 'panel';

  const [agent, setAgent] = useState<MarketplaceAgentDetail | null>(null);
  const [conversations, setConversations] = useState<MarketplaceConversation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);

  // Rating state
  const [myRating, setMyRating] = useState<number | null>(null);
  const [ratingSubmitting, setRatingSubmitting] = useState(false);

  const loadData = useCallback(async () => {
    if (!numericId || Number.isNaN(numericId)) {
      setError('Invalid agent ID');
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const [detail, convData, ratingData] = await Promise.all([
        apiService.getMarketplaceAgentDetail(numericId),
        apiService.getMarketplaceConversations(100, 0),
        apiService.getMyMarketplaceRating(numericId),
      ]);
      setAgent(detail);
      setConversations(
        convData.conversations.filter((c) => c.agent_id === numericId),
      );
      setMyRating(ratingData.rating);
    } catch (err) {
      setError(getAgentLoadError(err));
    } finally {
      setLoading(false);
    }
  }, [numericId]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  const handleStartChat = useCallback(async () => {
    if (!agent || starting) return;
    setStarting(true);
    try {
      const conv = await mutate(
        () => apiService.createMarketplaceConversation(agent.agent_id),
        {
          loading: 'Starting conversation…',
          success: 'Conversation started',
          error: (err) => errorMessage(err, 'Failed to start conversation'),
        },
      );
      if (!conv) return;
      navigate(`/marketplace/chat/${conv.conversation_id ?? conv.id}`);
    } finally {
      setStarting(false);
    }
  }, [agent, starting, mutate, navigate]);

  const handleRate = useCallback(
    async (rating: number) => {
      if (!agent || ratingSubmitting) return;
      setRatingSubmitting(true);
      const result = await mutate(
        () => apiService.rateMarketplaceAgent(agent.agent_id, rating),
        {
          loading: 'Submitting rating…',
          success: 'Rating saved',
          error: (err) => errorMessage(err, 'Failed to submit rating'),
        },
      );
      setRatingSubmitting(false);
      if (!result) return;

      setMyRating(result.rating);
      setAgent((prev) =>
        prev
          ? { ...prev, rating_avg: result.rating_avg, rating_count: result.rating_count }
          : prev,
      );
    },
    [agent, mutate, ratingSubmitting],
  );

  if (loading) {
    return <LoadingState message="Loading agent details..." />;
  }

  if (error) {
    if (isPanel) return <ErrorState error={error} onRetry={loadData} />;
    return (
      <div className="space-y-4">
        <ErrorState error={error} onRetry={loadData} />
        <div className="text-center">
          <Link
            to="/marketplace"
            className="text-sm text-blue-600 hover:text-blue-800 underline inline-flex items-center gap-1"
          >
            <ArrowLeft className="w-4 h-4" /> Back to Marketplace
          </Link>
        </div>
      </div>
    );
  }

  if (!agent) return null;

  const publishedDate = agent.published_at
    ? new Date(agent.published_at).toLocaleDateString()
    : null;

  const hasConversation = conversations.length > 0;

  if (isPanel) {
    return (
      <MarketplaceAgentPanelView
        agent={agent}
        conversations={conversations}
        publishedDate={publishedDate}
        myRating={myRating}
        ratingSubmitting={ratingSubmitting}
        starting={starting}
        onStartChat={handleStartChat}
        onRate={handleRate}
      />
    );
  }

  return (
    <div className="space-y-6">
      {/* Back link */}
      <Link
        to="/marketplace"
        className="inline-flex items-center gap-1 text-sm text-gray-500 hover:text-gray-700"
      >
        <ArrowLeft className="w-4 h-4" /> Back to Marketplace
      </Link>

      {/* Cover image / gradient banner */}
      <div className="rounded-lg overflow-hidden h-40 md:h-52">
        {agent.cover_image_url ? (
          <img
            src={agent.cover_image_url}
            alt={`${agent.display_name} cover`}
            className="w-full h-full object-cover"
          />
        ) : (
          <div className="w-full h-full bg-gradient-to-r from-blue-500 to-indigo-600" />
        )}
      </div>

      {/* Agent header */}
      <div className="flex flex-col sm:flex-row gap-4 -mt-10 sm:-mt-12 px-4 sm:px-0 relative z-10">
        {/* Icon */}
        <div className="flex-shrink-0 w-20 h-20 rounded-xl bg-white shadow-md border flex items-center justify-center overflow-hidden">
          {agent.icon_url ? (
            <img
              src={agent.icon_url}
              alt={agent.display_name}
              className="w-full h-full object-cover rounded-xl"
            />
          ) : (
            <Bot className="w-10 h-10 text-blue-400" aria-hidden="true" />
          )}
        </div>

        {/* Name, publisher, badges */}
        <div className="flex-1 pt-2">
          <h1 className="text-2xl font-bold text-gray-900">
            {agent.display_name}
          </h1>
          <p className="text-sm text-gray-500 mt-0.5">by {agent.app_name}</p>

          {/* Rating summary */}
          <RatingSummary
            ratingAvg={agent.rating_avg}
            ratingCount={agent.rating_count}
            conversationCount={agent.conversation_count}
          />

          <div className="flex flex-wrap items-center gap-2 mt-2">
            {agent.category && (
              <Badge
                label={agent.category}
                variant={CATEGORY_VARIANT[agent.category] ?? 'default'}
              />
            )}
            {agent.has_knowledge_base && (
              <Badge label="Knowledge-enhanced" variant="success" icon="📚" />
            )}
            {agent.has_memory && (
              <Badge label="Memory" variant="info" icon="🧠" />
            )}
          </div>
        </div>

        {/* Action buttons (desktop) */}
        <div className="hidden sm:flex flex-col gap-2 pt-2">
          <ButtonApp
            label={starting ? 'Starting…' : 'Start New Chat'}
            onClick={handleStartChat}
            variant="primary"
            size="medium"
            loading={starting}
          />
        </div>
      </div>

      {/* Tags */}
      {agent.tags && agent.tags.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {agent.tags.map((tag) => (
            <Badge key={tag} label={tag} variant="default" />
          ))}
        </div>
      )}

      {/* Main content: description + sidebar */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Description */}
        <div className="lg:col-span-2">
          <div className="bg-white rounded-lg shadow-md border p-6">
            <h2 className="text-lg font-semibold text-gray-900 mb-4">About</h2>
            <AgentDescription agent={agent} />
          </div>
        </div>

        {/* Sidebar: info panel */}
        <div className="space-y-6">
          {/* Info card */}
          <div className="bg-white rounded-lg shadow-md border p-6">
            <h2 className="text-lg font-semibold text-gray-900 mb-4">Details</h2>
            <dl className="space-y-3 text-sm">
              <div className="flex justify-between">
                <dt className="text-gray-500">Memory</dt>
                <dd className="font-medium text-gray-900">
                  {agent.has_memory ? 'Enabled' : 'Disabled'}
                </dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-gray-500">Knowledge Base</dt>
                <dd className="font-medium text-gray-900">
                  {agent.has_knowledge_base ? 'Yes' : 'No'}
                </dd>
              </div>
              {publishedDate && (
                <div className="flex justify-between">
                  <dt className="text-gray-500">Published</dt>
                  <dd className="font-medium text-gray-900">{publishedDate}</dd>
                </div>
              )}
            </dl>
          </div>

          {/* Rating card */}
          <div className="bg-white rounded-lg shadow-md border p-6">
            <h2 className="text-lg font-semibold text-gray-900 mb-3">Rate this agent</h2>
            {hasConversation ? (
              <div className="space-y-2">
                <StarRating value={myRating} interactive size="md" onChange={handleRate} />
                {myRating !== null && !ratingSubmitting && (
                  <p className="text-xs text-gray-500">
                    Your rating: {myRating} star{myRating === 1 ? '' : 's'}. Click to change.
                  </p>
                )}
              </div>
            ) : (
              <div className="space-y-2">
                <StarRating value={null} size="md" />
                <p className="text-xs text-gray-500">
                  Start a conversation with this agent to leave a rating.
                </p>
              </div>
            )}
          </div>

          {/* Mobile action button */}
          <div className="sm:hidden">
            <ButtonApp
              label={starting ? 'Starting…' : 'Start New Chat'}
              onClick={handleStartChat}
              variant="primary"
              size="medium"
              loading={starting}
              className="w-full"
            />
          </div>

          {/* Existing conversations */}
          {conversations.length > 0 && (
            <div className="bg-white rounded-lg shadow-md border p-6">
              <h2 className="text-lg font-semibold text-gray-900 mb-4">
                Your Conversations
              </h2>
              <ul className="space-y-3">
                {conversations.map((conv) => (
                  <li key={conv.conversation_id}>
                    <Link
                      to={`/marketplace/chat/${conv.conversation_id}`}
                      className="block p-3 rounded-lg border hover:bg-gray-50 transition-colors"
                    >
                      <p className="text-sm font-medium text-gray-900 truncate">
                        {conv.title || 'Untitled conversation'}
                      </p>
                      {conv.last_message && (
                        <p className="text-xs text-gray-500 truncate mt-1">
                          {conv.last_message}
                        </p>
                      )}
                      <p className="text-xs text-gray-400 mt-1">
                        {new Date(conv.updated_at).toLocaleDateString()} ·{' '}
                        {conv.message_count} message{conv.message_count === 1 ? '' : 's'}
                      </p>
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/* ========== Sub-components ========== */

interface MarketplaceAgentPanelViewProps {
  readonly agent: MarketplaceAgentDetail;
  readonly conversations: MarketplaceConversation[];
  readonly publishedDate: string | null;
  readonly myRating: number | null;
  readonly ratingSubmitting: boolean;
  readonly starting: boolean;
  readonly onStartChat: () => void;
  readonly onRate: (rating: number) => void;
}

const PANEL_CARD =
  'rounded-xl border border-line dark:border-line-dark bg-surface dark:bg-surface-dark p-6';
const PANEL_CARD_TITLE =
  'font-display text-[17px] font-medium text-fg dark:text-fg-dark mb-3';
const PANEL_DT = 'text-fg-tertiary dark:text-fg-tertiary-dark';
const PANEL_DD_ON = 'font-medium text-success dark:text-success-dark';
const PANEL_DD_OFF = 'font-medium text-fg-tertiary dark:text-fg-tertiary-dark';

/** Compact single-column agent profile shown in the marketplace side panel. */
function MarketplaceAgentPanelView({
  agent,
  conversations,
  publishedDate,
  myRating,
  ratingSubmitting,
  starting,
  onStartChat,
  onRate,
}: MarketplaceAgentPanelViewProps) {
  const hasConversation = conversations.length > 0;

  return (
    <div className="space-y-5 px-4 py-4">
      {/* Header */}
      <div className="flex items-start gap-4">
          {agent.icon_url ? (
            <div className="flex-none w-[70px] h-[70px] rounded-lg border border-accent dark:border-accent-dark bg-surface dark:bg-surface-dark flex items-center justify-center overflow-hidden">
              <img src={agent.icon_url} alt={agent.display_name} className="w-full h-full object-cover" />
            </div>
          ) : (
            <BackgroundImage
              icon="Bot"
              alt={agent.display_name}
              size={70}
              variant="vacio"
            />
          )}
        
        <div className="min-w-0 flex-1">
          <h3 className="font-display text-[28px] leading-tight text-fg dark:text-fg-dark break-words">
            {agent.display_name}
          </h3>
          <p className="text-[16px] text-fg-tertiary dark:text-fg-tertiary-dark">by {agent.app_name}</p>
          <RatingSummary
            ratingAvg={agent.rating_avg}
            ratingCount={agent.rating_count}
            conversationCount={agent.conversation_count}
          />
        </div>
      </div>

      {/* Category, capabilities and tags */}
      <div className="flex flex-wrap items-center gap-2">
        {agent.category && (
          <Badge label={agent.category} variant={CATEGORY_VARIANT[agent.category] ?? 'default'} />
        )}
        {agent.has_knowledge_base && <Badge label="Knowledge" variant="success" />}
        {agent.has_memory && <Badge label="Memory" variant="info" />}
        {agent.tags?.map((tag) => <Badge key={tag} label={tag} variant="default" />)}
      </div>

      <ButtonApp
        label={starting ? 'Starting…' : 'Start New Chat'}
        onClick={onStartChat}
        variant="primary"
        size="medium"
        loading={starting}
        className="w-full"
      />

      {/* About */}
      <CardApp className={PANEL_CARD}>
        <h4 className={PANEL_CARD_TITLE}>About</h4>
        <div className="text-[15px] leading-relaxed text-fg-secondary dark:text-fg-secondary-dark">
          <AgentDescription agent={agent} />
        </div>
      </CardApp>

      {/* Details */}
      <CardApp className={PANEL_CARD}>
        <h4 className={PANEL_CARD_TITLE}>Details</h4>
        <dl className="space-y-3 text-[15px]">
          <div className="flex justify-between gap-4">
            <dt className={PANEL_DT}>Memory</dt>
            <dd className={agent.has_memory ? PANEL_DD_ON : PANEL_DD_OFF}>
              {agent.has_memory ? 'Enabled' : 'Disabled'}
            </dd>
          </div>
          <div className="flex justify-between gap-4">
            <dt className={PANEL_DT}>Knowledge Base</dt>
            <dd className={agent.has_knowledge_base ? PANEL_DD_ON : PANEL_DD_OFF}>
              {agent.has_knowledge_base ? 'Yes' : 'No'}
            </dd>
          </div>
          {publishedDate && (
            <div className="flex justify-between gap-4">
              <dt className={PANEL_DT}>Published</dt>
              <dd className="font-medium text-fg dark:text-fg-dark">{publishedDate}</dd>
            </div>
          )}
        </dl>
      </CardApp>

      {/* Rating */}
      <CardApp className={PANEL_CARD}>
        <h4 className={PANEL_CARD_TITLE}>Rate this agent</h4>
        <div className="space-y-2">
          {hasConversation ? (
            <>
              <StarRating value={myRating} interactive size="md" onChange={onRate} />
              {myRating !== null && !ratingSubmitting && (
                <p className="text-xs text-fg-tertiary dark:text-fg-tertiary-dark">
                  Your rating: {myRating} star{myRating === 1 ? '' : 's'}. Click to change.
                </p>
              )}
            </>
          ) : (
            <>
              <StarRating value={null} size="md" />
              <p className="text-xs text-fg-tertiary dark:text-fg-tertiary-dark">
                Start a conversation with this agent to leave a rating.
              </p>
            </>
          )}
        </div>
      </CardApp>

      {/* Existing conversations */}
      {hasConversation && (
        <CardApp className={PANEL_CARD}>
          <h4 className={PANEL_CARD_TITLE}>Your Conversations</h4>
          <ul className="space-y-3">
            {conversations.map((conv) => (
              <li key={conv.conversation_id}>
                <Link
                  to={`/marketplace/chat/${conv.conversation_id}`}
                  className="block p-3 rounded-lg border border-line dark:border-line-dark hover:bg-surface-hover dark:hover:bg-surface-hover-dark transition-colors"
                >
                  <p className="text-sm font-medium text-fg dark:text-fg-dark truncate">
                    {conv.title || 'Untitled conversation'}
                  </p>
                  {conv.last_message && (
                    <p className="text-xs text-fg-tertiary dark:text-fg-tertiary-dark truncate mt-1">
                      {conv.last_message}
                    </p>
                  )}
                  <p className="text-xs text-fg-faint dark:text-fg-faint-dark mt-1">
                    {new Date(conv.updated_at).toLocaleDateString()} ·{' '}
                    {conv.message_count} message{conv.message_count === 1 ? '' : 's'}
                  </p>
                </Link>
              </li>
            ))}
          </ul>
        </CardApp>
      )}
    </div>
  );
}

interface AgentDescriptionProps {
  readonly agent: MarketplaceAgentDetail;
}

function AgentDescription({ agent }: AgentDescriptionProps) {
  if (agent.long_description) {
    return (
      <div className="prose prose-sm max-w-none">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{agent.long_description}</ReactMarkdown>
      </div>
    );
  }
  if (agent.short_description) {
    return <p className="text-fg dark:text-fg-dark">{agent.short_description}</p>;
  }
  return <p className="text-fg-tertiary dark:text-fg-tertiary-dark italic">No description available.</p>;
}
