import { useState, useEffect } from 'react';
import { Pencil, Plus, RefreshCw, Trash2 } from 'lucide-react';
import { apiService } from '../../services/api';
import { useConfirm } from '../../contexts/ConfirmContext';
import Alert from '../ui/Alert';
import ButtonApp from '../ui/ButtonApp';
import { LoadingState } from '../ui/LoadingState';

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
  onReloadRequest: _onReloadRequest
}: ConversationSidebarProps) {
  const confirm = useConfirm();
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isCollapsed, setIsCollapsed] = useState(false);
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
        <div className="p-6 text-center text-gray-500">
          <svg className="w-16 h-16 mx-auto mb-3 text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
          </svg>
          <p className="text-sm text-gray-600 dark:text-gray-400">No hay conversaciones aún</p>
          <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">Crea una nueva para empezar</p>
        </div>
      );
    }

    return (
      <div className="overflow-hidden rounded-md border border-line dark:border-line-dark">
        {conversations.map((conversation) => {
          const isActive = conversation.conversation_id === currentConversationId;
          const isEditing = editingConvId === conversation.conversation_id;

          return (
            <div
              key={conversation.conversation_id}
              className={`group flex items-start gap-2 border-b border-line bg-white px-2.5 py-[9px] transition-colors duration-150 last:border-b-0 hover:bg-surface-hover dark:border-line-dark dark:bg-surface-dark dark:hover:bg-surface-hover-dark ${
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
                    onClick={() => onConversationSelect(conversation.conversation_id)}
                    aria-current={isActive ? 'page' : undefined}
                    className="w-full text-left"
                  >
                    <span className="flex min-w-0 items-baseline gap-2">
                      <span className="min-w-0 flex-1 truncate text-[13.5px] font-medium text-fg dark:text-fg-dark">
                        {conversation.title || 'New conversation'}
                      </span>
                      <time className="flex-none text-[11.5px] text-fg-tertiary dark:text-fg-tertiary-dark">
                        {formatDate(conversation.updated_at)}
                      </time>
                    </span>
                    {conversation.last_message && (
                      <span className="mt-[3px] block max-w-full truncate text-[12.5px] leading-snug text-fg-tertiary dark:text-fg-tertiary-dark">
                        {conversation.last_message}
                      </span>
                    )}
                  </button>
                )}

                <div className="mt-1 text-[11px] text-fg-tertiary dark:text-fg-tertiary-dark">
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

  if (isCollapsed) {
    return (
      <div className="w-14 shrink-0 bg-canvas-alt dark:bg-canvas-alt-dark border-[0.5px] border-line dark:border-line-dark flex flex-col h-[calc(100vh-20rem)] min-h-[480px] items-center py-4">
        <button
          onClick={() => setIsCollapsed(false)}
          className="shrink-0 p-2 hover:bg-white/30 dark:hover:bg-gray-700/40 rounded-lg transition-colors"
          title="Expandir conversaciones"
        >
          <svg className="w-6 h-6 text-fg dark:text-fg-dark" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
          </svg>
        </button>

        <div className="flex min-h-0 flex-1 items-center justify-center overflow-hidden">
          <div className="whitespace-nowrap text-xs text-fg dark:text-fg-dark" style={{ transform: 'rotate(-90deg)', transformOrigin: 'center' }}>
            {conversations.length} conversaciones
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="w-80 shrink-0 bg-canvas-alt dark:bg-canvas-alt-dark border-[0.5px] border-line dark:border-line-dark flex flex-col h-[calc(100vh-20rem)] min-h-[480px] animate-fade-in">
      {/* Header */}
      <div className="p-4 border-b border-white/10 dark:border-gray-700/30">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-lg font-semibold text-gray-800 dark:text-gray-100">Conversaciones</h3>
          <button
            onClick={() => setIsCollapsed(true)}
            className="p-1 hover:bg-white/30 dark:hover:bg-gray-700/40 rounded transition-colors"
            title="Contraer"
          >
            <svg className="w-5 h-5 text-fg dark:text-fg-dark" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
            </svg>
          </button>
        </div>
        
        <ButtonApp
          label="Nueva Conversación"
          variant="primary"
          size="medium"
          onClick={onNewConversation}
          icon={<Plus className="h-5 w-5" aria-hidden="true" />}
          className="w-full shadow-sm hover:shadow-md"
        />
      </div>

      {/* Conversations List */}
      <div className="flex-1 overflow-y-auto p-2">
        {renderContent()}
      </div>
      
      {/* Footer */}
      <div className="p-3 border-t border-white/10 dark:border-gray-700/30">
        <ButtonApp
          label="Actualizar"
          variant="secondary"
          size="compact"
          onClick={loadConversations}
          icon={<RefreshCw className="h-4 w-4" aria-hidden="true" />}
          className="w-full"
        />
      </div>
    </div>
  );
}

