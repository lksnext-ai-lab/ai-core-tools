import { useState, useEffect } from 'react';
import { Pencil, Trash2 } from 'lucide-react';
import { apiService } from '../../services/api';
import { useConfirm } from '../../contexts/ConfirmContext';
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

function formatDate(dateString: string): string {
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);

  if (diffMins < 1) return 'Ahora';
  if (diffMins < 60) return `Hace ${diffMins}m`;
  if (diffHours < 24) return `Hace ${diffHours}h`;
  if (diffDays < 7) return `Hace ${diffDays}d`;

  return date.toLocaleDateString('es-ES', { 
    day: 'numeric', 
    month: 'short' 
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
      setError('Error al cargar conversaciones');
    } finally {
      setLoading(false);
    }
  }

  async function handleDeleteConversation(conversationId: number, e: React.MouseEvent) {
    e.stopPropagation();

    const ok = await confirm({
      title: 'Delete conversation',
      message: 'Are you sure you want to delete this conversation? This action cannot be undone.',
      confirmLabel: 'Delete',
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
      alert('Error al eliminar conversación');
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
      alert('Error al actualizar título');
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
        <LoadingState variant="section" message="Loading conversations..." />
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
                Reintentar
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
          <p className="text-[13px] text-fg-tertiary dark:text-fg-tertiary-dark">No hay conversaciones aún</p>
          <p className="mt-1 text-[12px] text-fg-tertiary dark:text-fg-tertiary-dark">Crea una nueva para empezar</p>
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
                        {conversation.title || 'New conversation'}
                      </span>
                      <time className="flex-none text-[11px] text-fg-tertiary dark:text-fg-tertiary-dark">
                        {formatDate(conversation.updated_at)}
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
                  {conversation.message_count} mensajes
                </div>
              </div>

              {!isEditing && (
                <div className="flex shrink-0 items-center gap-1">
                  <button
                    type="button"
                    data-action="rename"
                    onClick={(e) => handleRenameStart(e, conversation)}
                    aria-label="Renombrar conversación"
                    title="Renombrar conversación"
                    className="flex h-8 w-8 items-center justify-center text-fg-tertiary opacity-0 transition group-hover:opacity-100 focus:opacity-100 hover:text-fg-secondary dark:text-fg-tertiary-dark dark:hover:text-fg-secondary-dark"
                  >
                    <Pencil className="h-3.5 w-3.5" aria-hidden="true" />
                  </button>
                  <button
                    type="button"
                    data-action="delete"
                    onClick={(e) => handleDeleteConversation(conversation.conversation_id, e)}
                    aria-label="Eliminar conversación"
                    title="Eliminar conversación"
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
      title="Conversaciones"
      closeLabel="Cerrar conversaciones"
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
          Nueva
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
          Actualizar
        </button>
      }
    >
      {renderContent()}
    </SidePanel>
  );
}

