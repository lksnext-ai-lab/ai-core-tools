import { useState, useEffect } from 'react';
import { apiService } from '../../services/api';

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
  agentId: number;
  currentConversationId?: number | null;
  onConversationSelect: (conversationId: number) => void;
  onNewConversation: () => void;
  onReloadRequest?: () => void;
}

export default function ConversationSidebar({
  agentId,
  currentConversationId,
  onConversationSelect,
  onNewConversation,
  onReloadRequest
}: ConversationSidebarProps) {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState<number | null>(null);

  useEffect(() => {
    loadConversations();
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
    
    if (deleteConfirm === conversationId) {
      try {
        await apiService.deleteConversation(conversationId);
        setConversations(conversations.filter(c => c.conversation_id !== conversationId));
        
        // If deleting current conversation, trigger new conversation
        if (currentConversationId === conversationId) {
          onNewConversation();
        }
        
        setDeleteConfirm(null);
      } catch (err) {
        console.error('Error deleting conversation:', err);
        alert('Error al eliminar conversación');
      }
    } else {
      setDeleteConfirm(conversationId);
      setTimeout(() => setDeleteConfirm(null), 3000);
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

  if (isCollapsed) {
    return (
      <div className="w-12 bg-gray-50 border-r border-gray-200 flex flex-col items-center py-4">
        <button
          onClick={() => setIsCollapsed(false)}
          className="p-2 hover:bg-gray-200 rounded-lg transition-colors"
          title="Expandir conversaciones"
        >
          <svg className="w-6 h-6 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
          </svg>
        </button>
        
        <div className="mt-4 text-xs text-gray-500 transform -rotate-90 whitespace-nowrap">
          {conversations.length} conversaciones
        </div>
      </div>
    );
  }

  return (
    <div className="w-80 bg-gray-50 border-r border-gray-200 flex flex-col">
      {/* Header */}
      <div className="p-4 border-b border-gray-200">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-lg font-semibold text-gray-900">Conversaciones</h3>
          <button
            onClick={() => setIsCollapsed(true)}
            className="p-1 hover:bg-gray-200 rounded transition-colors"
            title="Contraer"
          >
            <svg className="w-5 h-5 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
            </svg>
          </button>
        </div>
        
        <button
          onClick={onNewConversation}
          className="w-full px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors flex items-center justify-center space-x-2"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          <span>Nueva Conversación</span>
        </button>
      </div>

      {/* Conversations List */}
      <div className="flex-1 overflow-y-auto">
        {loading ? (
          <div className="flex items-center justify-center p-8">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
          </div>
        ) : error ? (
          <div className="p-4 text-center text-red-600">
            <p>{error}</p>
            <button 
              onClick={loadConversations}
              className="mt-2 text-sm text-blue-600 hover:underline"
            >
              Reintentar
            </button>
          </div>
        ) : conversations.length === 0 ? (
          <div className="p-6 text-center text-gray-500">
            <svg className="w-16 h-16 mx-auto mb-3 text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
            </svg>
            <p className="text-sm">No hay conversaciones aún</p>
            <p className="text-xs text-gray-400 mt-1">Crea una nueva para empezar</p>
          </div>
        ) : (
          <div className="divide-y divide-gray-200">
            {conversations.map((conversation) => {
              const isActive = conversation.conversation_id === currentConversationId;
              const isDeleteConfirming = deleteConfirm === conversation.conversation_id;
              
              return (
                <div
                  key={conversation.conversation_id}
                  onClick={() => onConversationSelect(conversation.conversation_id)}
                  className={`p-4 cursor-pointer transition-colors ${
                    isActive 
                      ? 'bg-blue-50 border-l-4 border-blue-600' 
                      : 'hover:bg-gray-100 border-l-4 border-transparent'
                  }`}
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-1 min-w-0">
                      <h4 className={`text-sm font-medium truncate ${
                        isActive ? 'text-blue-900' : 'text-gray-900'
                      }`}>
                        {conversation.title}
                      </h4>
                      
                      {conversation.last_message && (
                        <p className="text-xs text-gray-500 truncate mt-1">
                          {conversation.last_message}
                        </p>
                      )}
                      
                      <div className="flex items-center space-x-2 mt-2 text-xs text-gray-400">
                        <span>{formatDate(conversation.updated_at)}</span>
                        <span>•</span>
                        <span>{conversation.message_count} mensajes</span>
                      </div>
                    </div>
                    
                    <button
                      onClick={(e) => handleDeleteConversation(conversation.conversation_id, e)}
                      className={`ml-2 p-1 rounded transition-colors ${
                        isDeleteConfirming 
                          ? 'bg-red-100 text-red-600 hover:bg-red-200' 
                          : 'text-gray-400 hover:text-red-600 hover:bg-red-50'
                      }`}
                      title={isDeleteConfirming ? 'Clic de nuevo para confirmar' : 'Eliminar conversación'}
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                      </svg>
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
      
      {/* Footer */}
      <div className="p-3 border-t border-gray-200 bg-white">
        <button
          onClick={loadConversations}
          className="w-full text-xs text-gray-600 hover:text-gray-900 transition-colors flex items-center justify-center space-x-1"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
          <span>Actualizar</span>
        </button>
      </div>
    </div>
  );
}

