import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { ArrowLeft, Bot} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { apiService } from '../services/api';
import { LoadingState } from '../components/ui/LoadingState';
import { ErrorState } from '../components/ui/ErrorState';
import { Badge } from '../components/ui/Badge';
import { StarRating } from '../components/marketplace/StarRating';
import type {
  MarketplaceAgentDetail,
  MarketplaceConversation,
} from '../types/marketplace';

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
        <span className="text-sm text-gray-400">No ratings yet</span>
      ) : (
        <span className="text-sm text-gray-600">
          {ratingAvg.toFixed(1)}{' '}
          <span className="text-gray-400">({ratingCount} rating{ratingCount === 1 ? '' : 's'})</span>
        </span>
      )}
      {conversationCount > 0 && (
        <span className="text-sm text-gray-400">
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

/**
 * Marketplace agent detail page — full profile view with description,
 * metadata, existing conversations, and "Start Chat" action.
 */
export default function MarketplaceAgentDetailPage() {
  const { agentId } = useParams<{ agentId: string }>();
  const navigate = useNavigate();
  const numericId = Number(agentId);

  const [agent, setAgent] = useState<MarketplaceAgentDetail | null>(null);
  const [conversations, setConversations] = useState<MarketplaceConversation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);

  // Rating state
  const [myRating, setMyRating] = useState<number | null>(null);
  const [ratingSubmitting, setRatingSubmitting] = useState(false);
  const [ratingError, setRatingError] = useState<string | null>(null);

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
    loadData();
  }, [loadData]);

  const handleStartChat = useCallback(async () => {
    if (!agent) return;
    setStarting(true);
    try {
      const conv = await apiService.createMarketplaceConversation(agent.agent_id);
      navigate(`/marketplace/chat/${conv.conversation_id ?? conv.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start conversation');
    } finally {
      setStarting(false);
    }
  }, [agent, navigate]);

  const handleRate = useCallback(async (rating: number) => {
    if (!agent || ratingSubmitting) return;
    setRatingSubmitting(true);
    setRatingError(null);
    try {
      const result = await apiService.rateMarketplaceAgent(agent.agent_id, rating);
      setMyRating(result.rating);
      setAgent((prev) =>
        prev
          ? { ...prev, rating_avg: result.rating_avg, rating_count: result.rating_count }
          : prev,
      );
    } catch (err) {
      setRatingError(err instanceof Error ? err.message : 'Failed to submit rating');
    } finally {
      setRatingSubmitting(false);
    }
  }, [agent, ratingSubmitting]);

  if (loading) {
    return <LoadingState message="Loading agent details..." />;
  }

  if (error) {
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
          <button
            type="button"
            onClick={handleStartChat}
            disabled={starting}
            className="px-6 py-2.5 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {starting ? 'Starting…' : 'Start New Chat'}
          </button>
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
                {ratingSubmitting && (
                  <p className="text-xs text-gray-500">Submitting…</p>
                )}
                {myRating !== null && !ratingSubmitting && (
                  <p className="text-xs text-gray-500">
                    Your rating: {myRating} star{myRating === 1 ? '' : 's'}. Click to change.
                  </p>
                )}
                {ratingError && (
                  <p className="text-xs text-red-500">{ratingError}</p>
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
            <button
              type="button"
              onClick={handleStartChat}
              disabled={starting}
              className="w-full px-6 py-2.5 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {starting ? 'Starting…' : 'Start New Chat'}
            </button>
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
    return <p className="text-gray-600">{agent.short_description}</p>;
  }
  return <p className="text-gray-400 italic">No description available.</p>;
}
