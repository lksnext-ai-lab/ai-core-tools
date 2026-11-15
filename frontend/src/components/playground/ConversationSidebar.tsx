import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import { Pencil, Trash2 } from 'lucide-react';
import { apiService } from '../../services/api';
import { useConfirm } from '../../contexts/ConfirmContext';
import Alert from '../ui/Alert';
import { LoadingState } from '../ui/LoadingState';
import { SidePanel } from '../ui/SidePanel';

/** The Chat's conversations have no `agent_id` / `session_id`, and may have no title yet. */
export interface SidebarConversation {
  conversation_id: number;
  agent_id?: number;
  user_id?: number;
  title?: string | null;
  session_id?: string;
  created_at: string;
  updated_at: string;
  last_message?: string | null;
  message_count: number;
}

interface ConversationSidebarProps {
  /** Needed by the default (playground) loaders; ignored when every callback below is given. */
  readonly agentId?: number;
  /** Default: the agent's conversations. */
  readonly loadConversations?: () => Promise<{ conversations?: readonly SidebarConversation[] }>;
  /** Default: renames through the generic conversation endpoint. */
  readonly renameConversation?: (conversationId: number, title: string) => Promise<unknown>;
  /** Default: deletes through the generic conversation endpoint. */
  readonly deleteConversation?: (conversationId: number) => Promise<unknown>;
  readonly currentConversationId?: number | null;
  readonly onConversationSelect: (conversationId: number) => void;
  readonly onNewConversation: () => void;
  readonly onReloadRequest?: () => void;
  /** Change it to refetch the list in place: no loading spinner once data is shown, so scroll, focus and an in-progress rename survive. */
  readonly refreshToken?: number;
  readonly open: boolean;
  readonly onClose: () => void;
}

interface DateFormatters {
  readonly date: Intl.DateTimeFormat;
  readonly relative: Intl.RelativeTimeFormat;
}

const formattersByLanguage = new Map<string, DateFormatters>();

/** One set of formatters per language. An invalid tag (e.g. i18next's `cimode`) falls back to the default locale. */
function getFormatters(language: string): DateFormatters {
  const cached = formattersByLanguage.get(language);
  if (cached) return cached;
  let locale: string | undefined = language;
  try {
    new Intl.DateTimeFormat(language);
  } catch {
    locale = undefined;
  }
  const formatters: DateFormatters = {
    date: new Intl.DateTimeFormat(locale, { day: 'numeric', month: 'short' }),
    relative: new Intl.RelativeTimeFormat(locale, { numeric: 'auto', style: 'long' }),
  };
  formattersByLanguage.set(language, formatters);
  return formatters;
}

interface FormattedDate {
  /** Short text shown on screen. */
  readonly visible: string;
  /** Unabbreviated text for assistive technology ("5 minutes ago"). */
  readonly spoken: string;
}

function formatDate(dateString: string, language: string, t: TFunction): FormattedDate {
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);
  const { date: dateFormat, relative } = getFormatters(language);

  if (diffMins < 1) return { visible: t('conversationSidebar.justNow'), spoken: relative.format(0, 'second') };
  if (diffMins < 60) {
    return { visible: t('conversationSidebar.minutesAgo', { value: diffMins }), spoken: relative.format(-diffMins, 'minute') };
  }
  if (diffHours < 24) {
    return { visible: t('conversationSidebar.hoursAgo', { value: diffHours }), spoken: relative.format(-diffHours, 'hour') };
  }
  if (diffDays < 7) {
    return { visible: t('conversationSidebar.daysAgo', { value: diffDays }), spoken: relative.format(-diffDays, 'day') };
  }

  const absolute = dateFormat.format(date);
  return { visible: absolute, spoken: absolute };
}

export default function ConversationSidebar({
  agentId,
  loadConversations: loadConversationsProp,
  renameConversation,
  deleteConversation,
  currentConversationId,
  onConversationSelect,
  onNewConversation,
  onReloadRequest: _onReloadRequest,
  refreshToken,
  open,
  onClose,
}: ConversationSidebarProps) {
  const { t, i18n } = useTranslation('common');
  const confirm = useConfirm();
  const [conversations, setConversations] = useState<readonly SidebarConversation[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadedOnce, setLoadedOnce] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editingConvId, setEditingConvId] = useState<number | null>(null);
  const [editingTitle, setEditingTitle] = useState('');

  useEffect(() => {
    void loadConversations();
  }, [agentId, refreshToken]);

  function requireAgentId(): number {
    if (agentId === undefined) {
      throw new Error('ConversationSidebar needs an agentId or custom conversation callbacks');
    }
    return agentId;
  }

  async function loadConversations() {
    try {
      if (!loadedOnce) setLoading(true);
      setError(null);
      const response = loadConversationsProp
        ? await loadConversationsProp()
        : await apiService.listConversations(requireAgentId());
      setConversations(response.conversations || []);
      setLoadedOnce(true);
    } catch (err) {
      console.error('Error loading conversations:', err);
      setError(t('conversationSidebar.loadError'));
    } finally {
      setLoading(false);
    }
  }

  async function handleDeleteConversation(conversationId: number, e: React.MouseEvent) {
    e.stopPropagation();

    const ok = await confirm({
      title: t('marketplaceHome.deleteConversation'),
      message: t('conversationSidebar.confirmDeleteMessage'),
      confirmLabel: t('delete'),
      variant: 'danger',
    });

    if (!ok) return;

    try {
      await (deleteConversation
        ? deleteConversation(conversationId)
        : apiService.deleteConversation(conversationId));
      setConversations(conversations.filter(c => c.conversation_id !== conversationId));

      if (currentConversationId === conversationId) {
        onNewConversation();
      }
    } catch (err) {
      console.error('Error deleting conversation:', err);
      alert(t('conversationSidebar.deleteFailed'));
    }
  }

  async function handleEditTitle(conversationId: number, newTitle: string) {
    try {
      await (renameConversation
        ? renameConversation(conversationId, newTitle)
        : apiService.updateConversation(conversationId, { title: newTitle }));
      setConversations(conversations.map(c => 
        c.conversation_id === conversationId ? { ...c, title: newTitle } : c
      ));
    } catch (err) {
      console.error('Error updating conversation title:', err);
      alert(t('conversationSidebar.renameFailed'));
    }
  }

  function handleRenameStart(e: React.MouseEvent, conversation: SidebarConversation) {
    e.stopPropagation();
    setEditingConvId(conversation.conversation_id);
    setEditingTitle(conversation.title || '');
  }

  async function handleRenameSave(conversationId: number) {
    const trimmed = editingTitle.trim();
    if (trimmed) {
      await handleEditTitle(conversationId, trimmed);
    }
    setEditingConvId(null);
  }

  function handleRenameKeyDown(e: React.KeyboardEvent, conversationId: number) {
    e.stopPropagation();
    if (e.key === 'Enter') {
      e.preventDefault();
      void handleRenameSave(conversationId);
    } else if (e.key === 'Escape') {
      setEditingConvId(null);
    }
  }

  const renderContent = () => {
    if (loading) {
      return (
        <LoadingState variant="section" message={t('conversationSidebar.loading')} />
      );
    }

    if (error) {
      return (
        <Alert
          type="error"
          message={(
            <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
              <span>{error}</span>
              <button
                type="button"
                onClick={() => void loadConversations()}
                className="font-medium text-error underline hover:text-error-strong dark:text-error-dark dark:hover:text-error-strong-dark"
              >
                {t('serviceUsage.retry')}
              </button>
            </div>
          )}
          className="m-3"
        />
      );
    }

    if (conversations.length === 0) {
      return (
        <div className="px-1.5 py-3">
          <p className="text-[13px] text-fg-tertiary dark:text-fg-tertiary-dark">{t('conversationSidebar.empty')}</p>
          <p className="mt-1 text-[12px] text-fg-tertiary dark:text-fg-tertiary-dark">{t('conversationSidebar.emptyHint')}</p>
        </div>
      );
    }

    return (
      <div>
        {conversations.map((conversation) => {
          const isActive = conversation.conversation_id === currentConversationId;
          const isEditing = editingConvId === conversation.conversation_id;
          const updatedAt = formatDate(conversation.updated_at, i18n.language, t);

          return (
            <div
              key={conversation.conversation_id}
              className={`group mb-0.5 flex items-start gap-2 rounded-md px-2.5 py-2.5 transition-colors duration-150 hover:bg-surface-hover dark:hover:bg-surface-hover-dark ${
                isActive ? 'bg-surface-hover dark:bg-surface-hover-dark' : ''
              }`}
            >
              <div className="min-w-0 flex-1">
                {isEditing ? (
                  <input
                    autoFocus
                    type="text"
                    value={editingTitle}
                    onChange={(e) => setEditingTitle(e.target.value)}
                    onBlur={() => handleRenameSave(conversation.conversation_id)}
                    onKeyDown={(e) => handleRenameKeyDown(e, conversation.conversation_id)}
                    aria-label={t('marketplaceHome.renameConversation')}
                    className="w-full min-w-0 border-b border-bronze bg-transparent py-1 text-sm font-medium text-fg outline-none dark:text-fg-dark"
                  />
                ) : (
                  <button
                    type="button"
                    onClick={() => {
                      onClose();
                      onConversationSelect(conversation.conversation_id);
                    }}
                    aria-current={isActive ? 'page' : undefined}
                    className="w-full text-left"
                  >
                    <span className="flex min-w-0 items-baseline justify-between gap-2">
                      <span className="min-w-0 flex-1 truncate text-[13px] font-medium text-fg dark:text-fg-dark">
                        {conversation.title || t('conversationSidebar.untitled')}
                      </span>
                      <time
                        dateTime={conversation.updated_at}
                        className="flex-none text-[11px] text-fg-tertiary dark:text-fg-tertiary-dark"
                      >
                        <span aria-hidden="true">{updatedAt.visible}</span>
                        <span className="sr-only">{updatedAt.spoken}</span>
                      </time>
                    </span>
                    {conversation.last_message && (
                      <span className="mt-0.5 block max-w-full truncate text-[12px] text-fg-secondary dark:text-fg-secondary-dark">
                        {conversation.last_message}
                      </span>
                    )}
                  </button>
                )}

                <div className="mt-[3px] text-[11px] text-fg-tertiary dark:text-fg-tertiary-dark">
                  {t('conversationSidebar.messageCount', { count: conversation.message_count })}
                </div>
              </div>

              {!isEditing && (
                <div className="flex shrink-0 items-center gap-1">
                  <button
                    type="button"
                    data-action="rename"
                    onClick={(e) => handleRenameStart(e, conversation)}
                    aria-label={t('marketplaceHome.renameConversation')}
                    title={t('marketplaceHome.renameConversation')}
                    className="flex h-8 w-8 items-center justify-center text-fg-tertiary opacity-0 transition group-hover:opacity-100 focus:opacity-100 hover:text-fg-secondary dark:text-fg-tertiary-dark dark:hover:text-fg-secondary-dark"
                  >
                    <Pencil className="h-3.5 w-3.5" aria-hidden="true" />
                  </button>
                  <button
                    type="button"
                    data-action="delete"
                    onClick={(e) => handleDeleteConversation(conversation.conversation_id, e)}
                    aria-label={t('marketplaceHome.deleteConversation')}
                    title={t('marketplaceHome.deleteConversation')}
                    className="flex h-8 w-8 items-center justify-center text-fg-tertiary opacity-0 transition group-hover:opacity-100 focus:opacity-100 hover:text-error dark:text-fg-tertiary-dark dark:hover:text-error-dark"
                  >
                    <Trash2 className="h-4 w-4" aria-hidden="true" />
                  </button>
                </div>
              )}
            </div>
          );
        })}
      </div>
    );
  };

  return (
    <SidePanel
      open={open}
      onClose={onClose}
      side="right"
      title={t('agentPlayground.conversations')}
      closeLabel={t('conversationSidebar.closeLabel')}
      widthClassName="w-[340px] max-w-full"
      headerActions={
        <button
          type="button"
          onClick={() => {
            onClose();
            onNewConversation();
          }}
          className="font-display text-[12.5px] px-[11px] py-[5px] rounded-md
                     border border-ink dark:border-ink-dark text-fg dark:text-fg-dark
                     hover:bg-surface-hover dark:hover:bg-surface-hover-dark transition-colors duration-150"
        >
          {t('conversationSidebar.new')}
        </button>
      }
      footer={
        <button
          type="button"
          onClick={() => void loadConversations()}
          className="w-full font-display text-[13px] px-3 py-2 rounded-md
                     border border-ink dark:border-ink-dark text-fg dark:text-fg-dark
                     hover:bg-surface-hover dark:hover:bg-surface-hover-dark transition-colors duration-150"
        >
          {t('conversationSidebar.refresh')}
        </button>
      }
    >
      {renderContent()}
    </SidePanel>
  );
}

