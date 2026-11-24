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
import { useTranslation } from 'react-i18next';

/** Parses an agent-load error into a user-friendly message. */
function getAgentLoadError(err: unknown, notFoundMessage: string, fallbackMessage: string): string {
  const msg = err instanceof Error ? err.message : fallbackMessage;
  if (msg.includes('404') || msg.includes('not found')) {
    return notFoundMessage;
  }
  return msg;
}

interface RatingSummaryProps {
  readonly ratingAvg: number | null;
  readonly ratingCount: number;
  readonly conversationCount: number;
}

function RatingSummary({ ratingAvg, ratingCount, conversationCount }: RatingSummaryProps) {
  const { t, i18n } = useTranslation('common');

  return (
    <div className="flex items-center gap-2 mt-1.5">
      <StarRating value={ratingAvg ? Math.round(ratingAvg) : null} size="md" />
      {ratingAvg === null ? (
        <span className="text-sm text-fg-default dark:text-fg-default-dark">
          {t('marketplaceAgentDetail.noRatingsYet')}
        </span>
      ) : (
        <span className="text-sm text-fg-default dark:text-fg-default-dark">
          {new Intl.NumberFormat(i18n.language, { minimumFractionDigits: 1, maximumFractionDigits: 1 }).format(ratingAvg)}{' '}
          <span className="text-fg-default dark:text-fg-default-dark">
            ({t('marketplaceAgentDetail.ratingCount', {
              count: ratingCount,
              formattedCount: ratingCount.toLocaleString(i18n.language),
            })})
          </span>
        </span>
      )}
      {conversationCount > 0 && (
        <span className="text-sm text-fg-default dark:text-fg-default-dark">
          · {t('marketplaceAgentDetail.conversationCount', {
            count: conversationCount,
            formattedCount: conversationCount.toLocaleString(i18n.language),
          })}
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

const CATEGORY_LABEL_KEYS: Record<string, string> = {
  Productivity: 'productivity',
  Research: 'research',
  Writing: 'writing',
  Code: 'code',
  'Data Analysis': 'dataAnalysis',
  'Customer Support': 'customerSupport',
  Education: 'education',
  Other: 'other',
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
  const { t, i18n } = useTranslation('common');
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
      setError(t('marketplaceAgentDetail.invalidAgentId'));
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
      setError(getAgentLoadError(
        err,
        t('marketplaceAgentDetail.agentUnavailable'),
        t('marketplaceAgentDetail.loadFailed'),
      ));
    } finally {
      setLoading(false);
    }
  }, [numericId, t]);

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
          loading: t('marketplacePage.startingConversation'),
          success: t('marketplacePage.conversationStarted'),
          error: (err) => errorMessage(err, t('marketplacePage.startConversationFailed')),
        },
      );
      if (!conv) return;
      navigate(`/marketplace/chat/${conv.conversation_id ?? conv.id}`);
    } finally {
      setStarting(false);
    }
  }, [agent, starting, mutate, navigate, t]);

  const handleRate = useCallback(
    async (rating: number) => {
      if (!agent || ratingSubmitting) return;
      setRatingSubmitting(true);
      const result = await mutate(
        () => apiService.rateMarketplaceAgent(agent.agent_id, rating),
        {
          loading: t('marketplaceAgentDetail.ratingSubmitting'),
          success: t('marketplaceAgentDetail.ratingSaved'),
          error: (err) => errorMessage(err, t('marketplaceAgentDetail.ratingFailed')),
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
    [agent, mutate, ratingSubmitting, t],
  );

  if (loading) {
    return <LoadingState message={t('marketplaceAgentDetail.loading')} />;
  }

  if (error) {
    if (isPanel) return <ErrorState error={error} onRetry={loadData} />;
    return (
      <div className="space-y-4">
        <ErrorState error={error} onRetry={loadData} />
        <div className="text-center">
          <Link
            to="/marketplace"
            className="text-sm text-bronze  dark:text-bronze-dark inline-block items-center gap-1"
          >
            <ArrowLeft className="w-4 h-4 inline-block ml-1" aria-hidden="true" /> {t('marketplaceChat.backToMarketplace')}
          </Link>
        </div>
      </div>
    );
  }

  if (!agent) return null;

  const publishedDate = agent.published_at
    ? new Date(agent.published_at).toLocaleDateString(i18n.language)
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
        className="inline-flex items-center gap-1 text-sm text-bronze  dark:text-bronze-dark"
      >
        <ArrowLeft className="w-4 h-4 inline-block ml-1" aria-hidden="true" /> {t('marketplaceChat.backToMarketplace')}
      </Link>

      {/* Cover image / gradient banner */}
      <div className="rounded-lg overflow-hidden h-40 md:h-52">
        {agent.cover_image_url ? (
          <img
            src={agent.cover_image_url}
            alt={t('marketplaceAgentDetail.coverImageAlt', { agent: agent.display_name })}
            className="w-full h-full object-cover"
          />
        ) : (
          <div className="w-full h-full bg-gradient-to-r from-bronze-border to-bronze-bg dark:from-bronze-border-dark dark:to-bronze-bg-dark" />
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
            <Bot className="w-10 h-10 text-bronze dark:text-bronze-dark" aria-hidden="true" />
          )}
        </div>

        {/* Name, publisher, badges */}
        <div className="flex-1 pt-2">
          <h1 className="text-2xl font-bold text-fg dark:text-fg-dark">
            {agent.display_name}
          </h1>
          <p className="text-sm text-fg-secondary dark:text-fg-secondary-dark mt-0.5">
            {t('marketplaceChat.publishedBy')} {agent.app_name}
          </p>

          {/* Rating summary */}
          <RatingSummary
            ratingAvg={agent.rating_avg}
            ratingCount={agent.rating_count}
            conversationCount={agent.conversation_count}
          />

          <div className="flex flex-wrap items-center gap-2 mt-2">
            {agent.category && (
              <Badge
                label={CATEGORY_LABEL_KEYS[agent.category]
                  ? t(`marketplacePage.categories.${CATEGORY_LABEL_KEYS[agent.category]}`)
                  : agent.category}
                variant={CATEGORY_VARIANT[agent.category] ?? 'default'}
              />
            )}
            {agent.has_knowledge_base && (
              <Badge label={t('marketplaceChat.knowledgeEnhanced')} variant="success" icon="📚" />
            )}
            {agent.has_memory && (
              <Badge label={t('marketplaceChat.memory')} variant="info" icon="🧠" />
            )}
          </div>
        </div>

        {/* Action buttons (desktop) */}
        <div className="hidden sm:flex flex-col gap-2 pt-2">
          <ButtonApp
            label={starting ? t('marketplaceAgentDetail.starting') : t('marketplaceAgentDetail.startNewChat')}
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
          <CardApp className="p-6" titulo={t('marketplaceAgentDetail.about')}>
            <AgentDescription agent={agent} />
          </CardApp>
        </div>

        {/* Sidebar: info panel */}
        <div className="space-y-6">
          {/* Info card */}
          <div className="bg-white rounded-lg shadow-md border p-6">
            <h2 className="text-md font-semibold text-fg dark:text-fg-dark mb-4">{t('marketplaceChat.details')}</h2>
            <dl className="space-y-3 text-sm">
              <div className="flex justify-between">
                <dt className="text-gray-500">{t('marketplaceChat.memory')}</dt>
                <dd className="font-medium text-gray-900">
                  {agent.has_memory ? t('marketplaceChat.enabled') : t('marketplaceChat.disabled')}
                </dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-gray-500">{t('marketplaceChat.knowledgeBase')}</dt>
                <dd className="font-medium text-gray-900">
                  {agent.has_knowledge_base ? t('marketplaceChat.yes') : t('marketplaceChat.no')}
                </dd>
              </div>
              {publishedDate && (
                <div className="flex justify-between">
                  <dt className="text-gray-500">{t('marketplaceChat.published')}</dt>
                  <dd className="font-medium text-gray-900">{publishedDate}</dd>
                </div>
              )}
            </dl>
          </div>

          {/* Rating card */}
          <div className="bg-white rounded-lg shadow-md border p-6">
            <h2 className="text-md font-semibold text-fg dark:text-fg-dark mb-3">
              {t('marketplaceAgentDetail.rateThisAgent')}
            </h2>
            {hasConversation ? (
              <div className="space-y-2">
                <StarRating value={myRating} interactive size="md" onChange={handleRate} />
                {myRating !== null && !ratingSubmitting && (
                  <p className="text-xs text-gray-500">
                    {t('marketplaceAgentDetail.yourRating', { count: myRating })}
                  </p>
                )}
              </div>
            ) : (
              <div className="space-y-2">
                <StarRating value={null} size="md" />
                <p className="text-xs text-gray-500">
                  {t('marketplaceAgentDetail.startConversationToRate')}
                </p>
              </div>
            )}
          </div>

          {/* Mobile action button */}
          <div className="sm:hidden">
            <ButtonApp
              label={starting ? t('marketplaceAgentDetail.starting') : t('marketplaceAgentDetail.startNewChat')}
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
                {t('marketplaceAgentDetail.yourConversations')}
              </h2>
              <ul className="space-y-3">
                {conversations.map((conv) => (
                  <li key={conv.conversation_id}>
                    <Link
                      to={`/marketplace/chat/${conv.conversation_id}`}
                      className="block p-3 rounded-lg border hover:bg-gray-50 transition-colors"
                    >
                      <p className="text-sm font-medium text-gray-900 truncate">
                        {conv.title || t('marketplaceAgentDetail.untitledConversation')}
                      </p>
                      {conv.last_message && (
                        <p className="text-xs text-gray-500 truncate mt-1">
                          {conv.last_message}
                        </p>
                      )}
                      <p className="text-xs text-gray-400 mt-1">
                        {new Date(conv.updated_at).toLocaleDateString(i18n.language)} ·{' '}
                        {t('marketplaceAgentDetail.messageCount', { count: conv.message_count })}
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
  const { t, i18n } = useTranslation('common');
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
              icon={Bot}
              alt={agent.display_name}
              size={70}
              variant="vacio"
            />
          )}
        
        <div className="min-w-0 flex-1">
          <h3 className="font-display text-[28px] leading-tight text-fg dark:text-fg-dark break-words">
            {agent.display_name}
          </h3>
          <p className="text-[16px] text-fg-tertiary dark:text-fg-tertiary-dark">
            {t('marketplaceChat.publishedBy')} {agent.app_name}
          </p>
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
          <Badge
            label={CATEGORY_LABEL_KEYS[agent.category]
              ? t(`marketplacePage.categories.${CATEGORY_LABEL_KEYS[agent.category]}`)
              : agent.category}
            variant={CATEGORY_VARIANT[agent.category] ?? 'default'}
          />
        )}
        {agent.has_knowledge_base && <Badge label={t('marketplacePage.knowledge')} variant="success" />}
        {agent.has_memory && <Badge label={t('marketplaceChat.memory')} variant="info" />}
        {agent.tags?.map((tag) => <Badge key={tag} label={tag} variant="default" />)}
      </div>

      <ButtonApp
        label={starting ? t('marketplaceAgentDetail.starting') : t('marketplaceAgentDetail.startNewChat')}
        onClick={onStartChat}
        variant="primary"
        size="medium"
        loading={starting}
        className="w-full"
      />

      {/* About */}
      <CardApp titulo={t('marketplaceAgentDetail.about')}>
        <div className="text-[15px] leading-relaxed text-fg-secondary dark:text-fg-secondary-dark">
          <AgentDescription agent={agent} />
        </div>
      </CardApp>

      {/* Details */}
      <CardApp titulo={t('marketplaceChat.details')}>
        <dl className="space-y-3 text-[15px]">
          <div className="flex justify-between gap-4">
            <dt className={PANEL_DT}>{t('marketplaceChat.memory')}</dt>
            <dd className={agent.has_memory ? PANEL_DD_ON : PANEL_DD_OFF}>
              {agent.has_memory ? t('marketplaceChat.enabled') : t('marketplaceChat.disabled')}
            </dd>
          </div>
          <div className="flex justify-between gap-4">
            <dt className={PANEL_DT}>{t('marketplaceChat.knowledgeBase')}</dt>
            <dd className={agent.has_knowledge_base ? PANEL_DD_ON : PANEL_DD_OFF}>
              {agent.has_knowledge_base ? t('marketplaceChat.yes') : t('marketplaceChat.no')}
            </dd>
          </div>
          {publishedDate && (
            <div className="flex justify-between gap-4">
              <dt className={PANEL_DT}>{t('marketplaceChat.published')}</dt>
              <dd className="font-medium text-fg dark:text-fg-dark">{publishedDate}</dd>
            </div>
          )}
        </dl>
      </CardApp>

      {/* Rating */}
      <CardApp titulo={t('marketplaceAgentDetail.rateThisAgent')}>
        <div className="space-y-2">
          {hasConversation ? (
            <>
              <StarRating value={myRating} interactive size="md" onChange={onRate} />
              {myRating !== null && !ratingSubmitting && (
                <p className="text-xs text-fg-tertiary dark:text-fg-tertiary-dark">
                  {t('marketplaceAgentDetail.yourRating', { count: myRating })}
                </p>
              )}
            </>
          ) : (
            <>
              <StarRating value={null} size="md" />
              <p className="text-xs text-fg-tertiary dark:text-fg-tertiary-dark">
                {t('marketplaceAgentDetail.startConversationToRate')}
              </p>
            </>
          )}
        </div>
      </CardApp>

      {/* Existing conversations */}
      {hasConversation && (
        <CardApp titulo={t('marketplaceAgentDetail.yourConversations')}>
          <ul className="space-y-3">
            {conversations.map((conv) => (
              <li key={conv.conversation_id}>
                <Link
                  to={`/marketplace/chat/${conv.conversation_id}`}
                  className="block p-3 rounded-lg border border-line dark:border-line-dark hover:bg-surface-hover dark:hover:bg-surface-hover-dark transition-colors"
                >
                  <p className="text-sm font-medium text-fg dark:text-fg-dark truncate">
                    {conv.title || t('marketplaceAgentDetail.untitledConversation')}
                  </p>
                  {conv.last_message && (
                    <p className="text-xs text-fg-tertiary dark:text-fg-tertiary-dark truncate mt-1">
                      {conv.last_message}
                    </p>
                  )}
                  <p className="text-xs text-fg-faint dark:text-fg-faint-dark mt-1">
                    {new Date(conv.updated_at).toLocaleDateString(i18n.language)} ·{' '}
                    {t('marketplaceAgentDetail.messageCount', { count: conv.message_count })}
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
  const { t } = useTranslation('common');

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
  return (
    <p className="text-fg-tertiary dark:text-fg-tertiary-dark italic">
      {t('marketplacePage.noDescriptionProvided')}
    </p>
  );
}
