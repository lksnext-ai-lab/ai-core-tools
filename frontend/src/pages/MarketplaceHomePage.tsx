import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {  MessageCircle, Store, ArrowRight, MessageSquare } from 'lucide-react';
import { toast } from 'sonner';
import { apiService } from '../services/api';
import { LoadingState } from '../components/ui/LoadingState';
import { ErrorState } from '../components/ui/ErrorState';
import { useConfirm } from '../contexts/ConfirmContext';
import { useApiMutation } from '../hooks/useApiMutation';
import { errorMessage } from '../constants/messages';
import type { MarketplaceConversation } from '../types/marketplace';
import Title from '../components/ui/Title';
import BackgroundImage from '../components/ui/BackgroundImage';
import ButtonApp from '../components/ui/ButtonApp';
import ButtonTab from '../components/ui/ButtonTab';
import ButtonTabItem from '../components/ui/ButtonTabItem';
import { CardApp } from '../components/ui/CardApp';
import { useTranslation } from 'react-i18next';

/** Simple relative-time formatter — no external dependency needed. */
function formatRelativeTime(dateStr: string, locale: string, justNowLabel: string): string {
  const diffMs = Date.now() - new Date(dateStr).getTime();
  const minutes = Math.floor(diffMs / 60_000);
  if (minutes < 1) return justNowLabel;
  const formatter = new Intl.RelativeTimeFormat(locale, { numeric: 'auto', style: 'short' });
  if (minutes < 60) return formatter.format(-minutes, 'minute');
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return formatter.format(-hours, 'hour');
  const days = Math.floor(hours / 24);
  return formatter.format(-days, 'day');
}

/**
 * Mini-dashboard landing page for USER-role consumers.
 * Shows recent marketplace conversations and a shortcut to browse agents.
 */
export default function MarketplaceHomePage() {
  const navigate = useNavigate();
  const confirm = useConfirm();
  const mutate = useApiMutation();
  const { t, i18n } = useTranslation('common');

  const [conversations, setConversations] = useState<MarketplaceConversation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editingConvId, setEditingConvId] = useState<number | null>(null);
  const [editingTitle, setEditingTitle] = useState('');

  useEffect(() => {
    let isMounted = true;

    async function fetchConversations() {
      try {
        setLoading(true);
        setError(null);
        const data = await apiService.getMarketplaceConversations(10, 0);
        if (isMounted) {
          setConversations(data.conversations);
        }
      } catch (err) {
        if (isMounted) {
          setError(errorMessage(err, t('marketplaceHome.loadConversationsFailed')));
        }
      } finally {
        if (isMounted) {
          setLoading(false);
        }
      }
    }

    void fetchConversations();

    return () => {
      isMounted = false;
    };
  }, []);

  async function handleDeleteConversation(conv: MarketplaceConversation) {
    const ok = await confirm({
      title: t('marketplaceHome.confirmDeleteTitle'),
      message: t('marketplaceHome.confirmDeleteMessage', { agent: conv.agent_display_name }),
      variant: 'danger',
      confirmLabel: t('delete'),
    });
    if (!ok) return;

    const result = await mutate(
      () => apiService.deleteConversation(conv.conversation_id),
      {
        loading: t('marketplaceHome.deletingConversation'),
        success: t('marketplaceHome.conversationDeleted'),
        error: (err) => errorMessage(err, t('marketplaceHome.deleteConversationFailed')),
      },
    );
    if (result === undefined) return;

    setConversations((prev) => prev.filter((c) => c.conversation_id !== conv.conversation_id));
  }

  function handleRenameStart(conv: MarketplaceConversation) {
    setEditingConvId(conv.conversation_id);
    setEditingTitle(conv.title || conv.agent_display_name);
  }

  async function handleRenameSave(conversationId: number) {
    const trimmed = editingTitle.trim();
    setEditingConvId(null);
    if (!trimmed) return;

    try {
      await apiService.updateConversation(conversationId, { title: trimmed });
      setConversations((prev) =>
        prev.map((c) =>
          c.conversation_id === conversationId ? { ...c, title: trimmed } : c,
        ),
      );
    } catch (err) {
      toast.error(errorMessage(err, t('marketplaceHome.renameConversationFailed')));
    }
  }

  if (loading) {
    return <LoadingState message={t('marketplaceHome.loadingDashboard')} />;
  }

  if (error) {
    return <ErrorState error={error} onRetry={() => globalThis.location.reload()} />;
  }

  return (
    <div className="max-w-4xl mx-auto space-y-8">
      <Title
        titulo={t('marketplaceHome.welcomeBack')}
        subtitulo={t('marketplaceHome.dashboardSubtitle')}
        variant="titPrincipal"
        subtitleMarginBottom={0}
      />  

      {/* Browse agents CTA */}
      <button
        type="button"
        onClick={() => navigate('/marketplace')}
        className="w-full text-left bg-btCard dark:bg-btCard-dark rounded-2xl shadow-sm border border-btCard-border dark:border-btCard-border-dark p-6 hover:border-btCard-hover dark:hover:bg-btCard-hover transition-all duration-200 group"
      >
        <div className="flex items-center gap-4">
          <BackgroundImage
            icon={Store}
            size={56}
            variant="marron"
            className="rounded-2xl"
          />
          <div className="flex-1 min-w-0">
            <h2 className="text-xl font-semibold text-fg dark:text-fg-dark ">
              {t('marketplaceHome.browseAgents')}
            </h2>
            <p className="text-fg-secondary dark:text-fg-secondary-dark text-sm mt-0.5">
              {t('marketplaceHome.discoverAgentsDescription')}
            </p>
          </div>
          <ArrowRight className="w-5 h-5 text-gray-400 group-hover:text-[var(--color-border-card-hover)] transition-colors duration-200" aria-hidden="true" />
        </div>
      </button>

      {/* Recent conversations */}
      <section>
        <h2 className="mb-4 block h-[23px] font-display text-[18px] font-normal tracking-[-0.36px] text-[var(--text-subtitle)]">{t('marketplaceHome.recentConversations')}</h2>

        {conversations.length === 0 ? (
          <CardApp className="p-10 flex items-center justify-center ">
            <BackgroundImage icon={MessageCircle} size={64} iconSize={32} variant="marron" className="mx-auto mb-4"></BackgroundImage>
            <h3 className="mb-4 block h-[23px] font-display text-[18px] font-normal tracking-[-0.36px] text-fg dark:text-fg-dark">{t('marketplaceHome.noConversations')}</h3>
            <p className="text-fg-secondary dark:text-fg-secondary-dark text-sm mt-0.5 mb-6">
              {t('marketplaceHome.noConversationsDescription')}
            </p>
            <ButtonApp
              label={t('marketplaceHome.browseAgents')}
              variant="primary"
              size="spacious"
              icon={<Store className="h-4 w-4" aria-hidden="true" />}
              onClick={() => navigate('/marketplace')}
            />
          </CardApp>
        ) : (
          <ButtonTab ariaLabel={t('marketplaceHome.recentConversations')}>
            {conversations.map((conv) => (
              <ButtonTabItem
                key={conv.conversation_id}
                title={conv.title || conv.agent_display_name}
                description={`${[conv.app_name, conv.agent_display_name].filter(Boolean).join(' · ')}\n${conv.last_message || t('marketplaceHome.noMessages')}`}
                dateTime={conv.updated_at}
                dateLabel={formatRelativeTime(conv.updated_at, i18n.resolvedLanguage ?? i18n.language, t('marketplaceHome.justNow'))}
                onClick={() => navigate(`/marketplace/chat/${conv.conversation_id}`)}
                icon={conv.agent_icon_url ? (
                  <img
                    src={conv.agent_icon_url}
                    alt=""
                    className="h-full w-full object-cover"
                    onError={(event) => { event.currentTarget.style.display = 'none'; }}
                  />
                ) : (
                  <BackgroundImage icon={MessageSquare} variant="marron" />
                )}
                variant="edit"
                isEditing={editingConvId === conv.conversation_id}
                editingTitle={editingTitle}
                onEdit={() => handleRenameStart(conv)}
                onDelete={() => handleDeleteConversation(conv)}
                onTitleChange={setEditingTitle}
                onSaveTitle={() => void handleRenameSave(conv.conversation_id)}
                onCancelEdit={() => setEditingConvId(null)}
              />
            ))}
          </ButtonTab>
        )}

      </section>
    </div>
  );
}
