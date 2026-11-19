import { useState, useEffect, useRef } from 'react';
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

/** DOM id of the panel; the control that opens it points to it with `aria-controls`. */
export const CONVERSATION_PANEL_ID = 'conversation-sidebar-panel';

type FocusRequest = { readonly kind: 'row' | 'rename'; readonly id: number } | { readonly kind: 'panel' };

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
  const [actionError, setActionError] = useState<string | null>(null);
  // Where focus goes after a row action removed or replaced the focused control.
  const [focusRequest, setFocusRequest] = useState<FocusRequest | null>(null);
  // Set once a rename was saved or cancelled, so the blur caused by the input unmounting does not save it again.
  const renameSettledRef = useRef(false);

  useEffect(() => {
    if (!focusRequest || typeof document === 'undefined') return;
    const target = focusRequest.kind === 'panel'
      ? document.getElementById(CONVERSATION_PANEL_ID)
      : document.getElementById(`${focusRequest.kind === 'rename' ? 'conversation-rename' : 'conversation-select'}-${focusRequest.id}`);
    target?.focus();
    setFocusRequest(null);
  }, [focusRequest]);

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
      cancelLabel: t('cancel'),
      variant: 'danger',
    });

    if (!ok) return;

    try {
      await (deleteConversation
        ? deleteConversation(conversationId)
        : apiService.deleteConversation(conversationId));
      // Focus moves to the row that takes its place (the next one, else the previous), else to the panel.
      const index = conversations.findIndex((c) => c.conversation_id === conversationId);
      const neighbour = conversations[index + 1] ?? conversations[index - 1];
      setConversations(conversations.filter(c => c.conversation_id !== conversationId));
      setFocusRequest(neighbour ? { kind: 'row', id: neighbour.conversation_id } : { kind: 'panel' });

      if (currentConversationId === conversationId) {
        onNewConversation();
      }
    } catch (err) {
      console.error('Error deleting conversation:', err);
      setActionError(t('conversationSidebar.deleteFailed'));
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
      setActionError(t('conversationSidebar.renameFailed'));
    }
  }

  function handleRenameStart(e: React.MouseEvent, conversation: SidebarConversation) {
    e.stopPropagation();
    renameSettledRef.current = false;
    setEditingConvId(conversation.conversation_id);
    setEditingTitle(conversation.title || '');
  }

  /** `restoreFocus`: after Enter / Esc focus goes back to the row; after a blur the user already went elsewhere. */
  async function handleRenameSave(conversationId: number, restoreFocus: boolean) {
    if (renameSettledRef.current) return;
    renameSettledRef.current = true;
    const trimmed = editingTitle.trim();
    setEditingConvId(null);
    if (restoreFocus) setFocusRequest({ kind: 'rename', id: conversationId });
    if (trimmed) {
      await handleEditTitle(conversationId, trimmed);
    }
  }

  function handleRenameCancel(conversationId: number) {
    renameSettledRef.current = true;
    setEditingConvId(null);
    setFocusRequest({ kind: 'rename', id: conversationId });
  }

  function handleRenameKeyDown(e: React.KeyboardEvent, conversationId: number) {
    e.stopPropagation();
    if (e.key === 'Enter') {
      e.preventDefault();
      void handleRenameSave(conversationId, true);
    } else if (e.key === 'Escape') {
      // Cancels without saving: the unmounting input must not save on blur.
      handleRenameCancel(conversationId);
    }
  }

  const renderBody = () => {
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
                {t('conversationSidebar.retry')}
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
          <p className="text-[13px] text-fg-secondary dark:text-fg-secondary-dark">{t('conversationSidebar.empty')}</p>
          <p className="mt-1 text-[12px] text-fg-secondary dark:text-fg-secondary-dark">{t('conversationSidebar.emptyHint')}</p>
        </div>
      );
    }

    return (
      <ul className="list-none p-0">
        {conversations.map((conversation) => {
          const isActive = conversation.conversation_id === currentConversationId;
          const isEditing = editingConvId === conversation.conversation_id;
          const updatedAt = formatDate(conversation.updated_at, i18n.language, t);
          const displayTitle = conversation.title || t('conversationSidebar.untitled');

          return (
            <li
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
                    onBlur={() => void handleRenameSave(conversation.conversation_id, false)}
                    onKeyDown={(e) => handleRenameKeyDown(e, conversation.conversation_id)}
                    aria-label={t('marketplaceHome.renameConversation')}
                    className="w-full min-w-0 border-b border-bronze bg-transparent py-1 text-sm font-medium text-fg outline-none dark:text-fg-dark"
                  />
                ) : (
                  <button
                    type="button"
                    id={`conversation-select-${conversation.conversation_id}`}
                    onClick={() => {
                      onClose();
                      onConversationSelect(conversation.conversation_id);
                    }}
                    aria-current={isActive ? 'true' : undefined}
                    className="w-full rounded text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus dark:focus-visible:ring-focus-dark"
                  >
                    <span className="flex min-w-0 items-baseline justify-between gap-2">
                      <span title={displayTitle} className="min-w-0 flex-1 truncate text-[13px] font-medium text-fg dark:text-fg-dark">
                        {displayTitle}
                      </span>
                      <time
                        dateTime={conversation.updated_at}
                        className="flex-none text-[11px] text-fg-secondary dark:text-fg-secondary-dark"
                      >
                        <span aria-hidden="true">{updatedAt.visible}</span>
                        <span className="sr-only">{updatedAt.spoken}</span>
                      </time>
                    </span>
                    {conversation.last_message && (
                      <span title={conversation.last_message} className="mt-0.5 block max-w-full truncate text-[12px] text-fg-secondary dark:text-fg-secondary-dark">
                        {conversation.last_message}
                      </span>
                    )}
                  </button>
                )}

                <div className="mt-[3px] text-[11px] text-fg-secondary dark:text-fg-secondary-dark">
                  {t('conversationSidebar.messageCount', { count: conversation.message_count })}
                </div>
              </div>

              {!isEditing && (
                <div className="flex shrink-0 items-center gap-1">
                  <button
                    type="button"
                    data-action="rename"
                    id={`conversation-rename-${conversation.conversation_id}`}
                    onClick={(e) => handleRenameStart(e, conversation)}
                    aria-label={t('conversationSidebar.renameNamed', { title: displayTitle })}
                    title={t('conversationSidebar.renameNamed', { title: displayTitle })}
                    className="flex h-8 w-8 items-center justify-center rounded text-fg-secondary opacity-0 transition group-hover:opacity-100 focus:opacity-100 [@media(hover:none)]:opacity-100 hover:text-fg dark:text-fg-secondary-dark dark:hover:text-fg-dark focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus dark:focus-visible:ring-focus-dark"
                  >
                    <Pencil className="h-3.5 w-3.5" aria-hidden="true" />
                  </button>
                  <button
                    type="button"
                    data-action="delete"
                    onClick={(e) => handleDeleteConversation(conversation.conversation_id, e)}
                    aria-label={t('conversationSidebar.deleteNamed', { title: displayTitle })}
                    title={t('conversationSidebar.deleteNamed', { title: displayTitle })}
                    className="flex h-8 w-8 items-center justify-center rounded text-fg-secondary opacity-0 transition group-hover:opacity-100 focus:opacity-100 [@media(hover:none)]:opacity-100 hover:text-error dark:text-fg-secondary-dark dark:hover:text-error-dark focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus dark:focus-visible:ring-focus-dark"
                  >
                    <Trash2 className="h-4 w-4" aria-hidden="true" />
                  </button>
                </div>
              )}
            </li>
          );
        })}
      </ul>
    );
  };

  const renderContent = () => (
    <>
      {actionError && (
        <Alert
          type="error"
          message={actionError}
          onDismiss={() => setActionError(null)}
          dismissAriaLabel={t('alert.dismissNamed', { name: t('agentPlayground.conversations') })}
          className="mb-2"
        />
      )}
      {renderBody()}
    </>
  );

  return (
    <SidePanel
      open={open}
      onClose={onClose}
      side="right"
      title={t('agentPlayground.conversations')}
      id={CONVERSATION_PANEL_ID}
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

