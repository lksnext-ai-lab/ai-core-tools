import { useState, useEffect } from 'react';
import { Pencil, Trash2 } from 'lucide-react';
import { apiService } from '../../services/api';
import { useConfirm } from '../../contexts/ConfirmContext';
import { useTranslation } from 'react-i18next';
import Alert from '../ui/Alert';
import { LoadingState } from '../ui/LoadingState';
import { SidePanel } from '../ui/SidePanel';

interface Conversation {
  conversation_id: number;
  agent_id: number;
  user_id?: number;
  title: string;
  session_id: string;
  created_at: string;
  updated_at: string;
  last_message?: string;
  message_count: number;
}

interface ConversationSidebarProps {
  readonly agentId: number;
  readonly currentConversationId?: number | null;
  readonly onConversationSelect: (conversationId: number) => void;
  readonly onNewConversation: () => void;
  readonly onReloadRequest?: () => void;
  readonly open: boolean;
  readonly onClose: () => void;
}

function formatDate(dateString: string, language: string): string {
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffSeconds = Math.floor(diffMs / 1000);
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);
  const relativeTime = new Intl.RelativeTimeFormat(language, { numeric: 'auto' });

  if (diffMins < 1) return relativeTime.format(-diffSeconds, 'second');
  if (diffMins < 60) return relativeTime.format(-diffMins, 'minute');
  if (diffHours < 24) return relativeTime.format(-diffHours, 'hour');
  if (diffDays < 7) return relativeTime.format(-diffDays, 'day');

  return date.toLocaleDateString(language, {
    day: 'numeric',
    month: 'short',
  });
}

export default function ConversationSidebar({
  agentId,
  currentConversationId,
  onConversationSelect,
  onNewConversation,
  onReloadRequest: _onReloadRequest,
  open,
  onClose,
}: ConversationSidebarProps) {
  const { t, i18n } = useTranslation('common');
  const confirm = useConfirm();
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editingConvId, setEditingConvId] = useState<number | null>(null);
  const [editingTitle, setEditingTitle] = useState('');

  useEffect(() => {
    void loadConversations();
  }, [agentId]);

  async function loadConversations() {
    try {
      setLoading(true);
      setError(null);
      const response = await apiService.listConversations(agentId);
      setConversations(response.conversations || []);
    } catch (err) {
      console.error('Error loading conversations:', err);
      setError(t('marketplaceHome.loadConversationsFailed'));
    } finally {
      setLoading(false);
    }
  }

  async function handleDeleteConversation(conversationId: number, e: React.MouseEvent) {
    e.stopPropagation();

    const title = conversations.find((conversation) => conversation.conversation_id === conversationId)?.title
      || t('marketplaceChat.newConversation');
    const ok = await confirm({
      title: t('marketplaceHome.confirmDeleteTitle'),
      message: t('marketplaceHome.confirmDeleteMessage', {
        agent: title,
      }),
      confirmLabel: t('marketplaceHome.deleteConversation'),
      variant: 'danger',
    });

    if (!ok) return;

    try {
      await apiService.deleteConversation(conversationId);
      setConversations(conversations.filter(c => c.conversation_id !== conversationId));

      if (currentConversationId === conversationId) {
        onNewConversation();
      }
    } catch (err) {
      console.error('Error deleting conversation:', err);
      alert(t('marketplaceHome.deleteConversationFailed'));
    }
  }

  async function handleEditTitle(conversationId: number, newTitle: string) {
    try {
      await apiService.updateConversation(conversationId, { title: newTitle });
      setConversations(conversations.map(c => 
        c.conversation_id === conversationId ? { ...c, title: newTitle } : c
      ));
    } catch (err) {
      console.error('Error updating conversation title:', err);
      alert(t('marketplaceHome.renameConversationFailed'));
    }
  }

  function handleRenameStart(e: React.MouseEvent, conversation: Conversation) {
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
        <LoadingState variant="section" message={t('agentPlayground.chat.loadingConversation')} />
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
          <p className="text-[13px] text-fg-tertiary dark:text-fg-tertiary-dark">{t('marketplaceHome.noConversations')}</p>
          <p className="mt-1 text-[12px] text-fg-tertiary dark:text-fg-tertiary-dark">{t('conversationSidebar.emptyDescription')}</p>
        </div>
      );
    }

    return (
      <div>
        {conversations.map((conversation) => {
          const isActive = conversation.conversation_id === currentConversationId;
          const isEditing = editingConvId === conversation.conversation_id;

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
                        {conversation.title || t('marketplaceChat.newConversation')}
                      </span>
                      <time className="flex-none text-[11px] text-fg-tertiary dark:text-fg-tertiary-dark">
                        {formatDate(conversation.updated_at, i18n.resolvedLanguage ?? i18n.language)}
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
                  {t('marketplaceAgentDetail.messageCount', { count: conversation.message_count })}
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
      closeLabel={t('conversationSidebar.close')}
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
          {t('marketplaceChat.newConversation')}
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

