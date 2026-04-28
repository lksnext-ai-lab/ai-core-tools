import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Bot, MessageCircle, Pencil, Store, ArrowRight, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { apiService } from '../services/api';
import { LoadingState } from '../components/ui/LoadingState';
import { ErrorState } from '../components/ui/ErrorState';
import { useConfirm } from '../contexts/ConfirmContext';
import { useApiMutation } from '../hooks/useApiMutation';
import { errorMessage, MESSAGES } from '../constants/messages';
import type { MarketplaceConversation } from '../types/marketplace';

/** Simple relative-time formatter — no external dependency needed. */
function formatRelativeTime(dateStr: string): string {
  const diffMs = Date.now() - new Date(dateStr).getTime();
  const minutes = Math.floor(diffMs / 60_000);
  if (minutes < 1) return 'just now';
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

/**
 * Mini-dashboard landing page for USER-role consumers.
 * Shows recent marketplace conversations and a shortcut to browse agents.
 */
export default function MarketplaceHomePage() {
  const navigate = useNavigate();
  const confirm = useConfirm();
  const mutate = useApiMutation();

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
          setError(errorMessage(err, 'Failed to load conversations'));
        }
      } finally {
        if (isMounted) {
          setLoading(false);
        }
      }
    }

    fetchConversations();

    return () => {
      isMounted = false;
    };
  }, []);

  async function handleDeleteConversation(e: React.MouseEvent, conv: MarketplaceConversation) {
    e.stopPropagation();
    const ok = await confirm({
      title: MESSAGES.CONFIRM_DELETE_TITLE('conversation'),
      message: `Delete the conversation with ${conv.agent_display_name}? This action cannot be undone.`,
      variant: 'danger',
      confirmLabel: 'Delete',
    });
    if (!ok) return;

    const result = await mutate(
      () => apiService.deleteConversation(conv.conversation_id),
      {
        loading: MESSAGES.DELETING('conversation'),
        success: MESSAGES.DELETED('conversation'),
        error: (err) => errorMessage(err, MESSAGES.DELETE_FAILED('conversation')),
      },
    );
    if (result === undefined) return;

    setConversations((prev) => prev.filter((c) => c.conversation_id !== conv.conversation_id));
  }

  function handleRenameStart(e: React.MouseEvent, conv: MarketplaceConversation) {
    e.stopPropagation();
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
      toast.error(errorMessage(err, 'Failed to rename conversation'));
    }
  }

  function handleRenameKeyDown(e: React.KeyboardEvent, conversationId: number) {
    e.stopPropagation();
    if (e.key === 'Enter') {
      e.preventDefault();
      handleRenameSave(conversationId);
    } else if (e.key === 'Escape') {
      setEditingConvId(null);
    }
  }

  if (loading) {
    return <LoadingState message="Loading your dashboard..." />;
  }

  if (error) {
    return <ErrorState error={error} onRetry={() => globalThis.location.reload()} />;
  }

  return (
    <div className="max-w-4xl mx-auto space-y-8">
      {/* Page header */}
      <div>
        <h1 className="text-3xl font-bold text-gray-900">Welcome back</h1>
        <p className="text-gray-600 mt-1">Your AI agent dashboard</p>
      </div>

      {/* Browse agents CTA */}
      <button
        type="button"
        onClick={() => navigate('/marketplace')}
        className="w-full text-left bg-white rounded-2xl shadow-sm border border-blue-200 p-6 hover:border-blue-400 hover:shadow-md transition-all duration-200 group"
      >
        <div className="flex items-center gap-4">
          <div className="w-14 h-14 bg-blue-100 rounded-2xl flex items-center justify-center shrink-0 group-hover:bg-blue-200 transition-colors duration-200">
            <Store className="w-7 h-7 text-blue-600" aria-hidden="true" />
          </div>
          <div className="flex-1 min-w-0">
            <h2 className="text-xl font-semibold text-gray-900 group-hover:text-blue-700 transition-colors duration-200">
              Browse Agents
            </h2>
            <p className="text-gray-500 text-sm mt-0.5">
              Discover and chat with AI agents published by your organisation
            </p>
          </div>
          <ArrowRight className="w-5 h-5 text-gray-400 group-hover:text-blue-500 transition-colors duration-200" aria-hidden="true" />
        </div>
      </button>

      {/* Recent conversations */}
      <section>
        <h2 className="text-xl font-semibold text-gray-900 mb-4">My Recent Conversations</h2>

        {conversations.length === 0 ? (
          <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-10 text-center">
            <div className="w-16 h-16 bg-gray-100 rounded-full flex items-center justify-center mx-auto mb-4">
              <MessageCircle className="w-8 h-8 text-gray-400" aria-hidden="true" />
            </div>
            <h3 className="text-lg font-medium text-gray-900 mb-2">No conversations yet</h3>
            <p className="text-gray-500 text-sm mb-6">
              You haven't chatted with any agents yet. Browse the marketplace to get started!
            </p>
            <button
              type="button"
              onClick={() => navigate('/marketplace')}
              className="inline-flex items-center px-5 py-2.5 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium rounded-xl transition-colors duration-200"
            >
              <Store className="w-4 h-4 mr-2" aria-hidden="true" />
              Browse Agents
            </button>
          </div>
        ) : (
          <ul className="space-y-3">
            {conversations.map((conv) => (
              <li key={conv.conversation_id} className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={(e) => {
                    if (editingConvId === conv.conversation_id) return;
                    if ((e.target as HTMLElement).closest('button[data-action]')) return;
                    navigate(`/marketplace/chat/${conv.conversation_id}`);
                  }}
                  className="flex-1 min-w-0 text-left bg-white rounded-xl shadow-sm border border-gray-200 p-4 hover:border-blue-300 hover:shadow-md transition-all duration-200 group"
                >
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-full bg-blue-100 flex items-center justify-center shrink-0 overflow-hidden">
                      {conv.agent_icon_url ? (
                        <img
                          src={conv.agent_icon_url}
                          alt=""
                          className="w-full h-full object-cover"
                          onError={(e) => { e.currentTarget.style.display = 'none'; }}
                        />
                      ) : (
                        <Bot className="w-5 h-5 text-blue-400" aria-hidden="true" />
                      )}
                    </div>

                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between gap-2">
                        <div className="flex items-center gap-1 min-w-0 flex-1">
                          {editingConvId === conv.conversation_id ? (
                            <input
                              autoFocus
                              type="text"
                              value={editingTitle}
                              onChange={(e) => setEditingTitle(e.target.value)}
                              onBlur={() => handleRenameSave(conv.conversation_id)}
                              onKeyDown={(e) => handleRenameKeyDown(e, conv.conversation_id)}
                              onClick={(e) => e.stopPropagation()}
                              className="text-sm font-semibold text-gray-900 border-b border-blue-500 outline-none bg-transparent w-full"
                            />
                          ) : (
                            <>
                              <span className="text-sm font-semibold text-gray-900 truncate group-hover:text-blue-700 transition-colors duration-200">
                                {conv.title || conv.agent_display_name}
                              </span>
                              <button
                                type="button"
                                data-action="rename"
                                onClick={(e) => handleRenameStart(e, conv)}
                                className="shrink-0 opacity-0 group-hover:opacity-100 p-0.5 rounded text-gray-400 hover:text-blue-500 transition-all"
                                title="Rename conversation"
                              >
                                <Pencil className="w-3 h-3" />
                              </button>
                            </>
                          )}
                        </div>
                        <time
                          dateTime={conv.updated_at}
                          className="text-xs text-gray-400 shrink-0"
                        >
                          {formatRelativeTime(conv.updated_at)}
                        </time>
                      </div>
                      <p className="text-xs text-gray-400 truncate mt-0.5">
                        {[conv.app_name, conv.agent_display_name].filter(Boolean).join(' · ')}
                      </p>
                      {conv.last_message ? (
                        <p className="text-xs text-gray-500 truncate mt-0.5">{conv.last_message}</p>
                      ) : (
                        <p className="text-xs text-gray-400 italic mt-0.5">No messages yet</p>
                      )}
                    </div>

                    <ArrowRight className="w-4 h-4 text-gray-300 group-hover:text-blue-400 transition-colors duration-200" aria-hidden="true" />
                  </div>
                </button>

                <button
                  type="button"
                  data-action="delete"
                  onClick={(e) => handleDeleteConversation(e, conv)}
                  title="Delete conversation"
                  className="shrink-0 p-2 rounded-lg text-gray-400 hover:text-red-500 hover:bg-red-50 transition-colors duration-200"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </li>
            ))}
          </ul>
        )}

        {conversations.length > 0 && (
          <div className="mt-4 text-center">
            <button
              type="button"
              onClick={() => navigate('/marketplace')}
              className="inline-flex items-center gap-1 text-sm text-blue-600 hover:text-blue-800 font-medium transition-colors duration-200"
            >
              Browse more agents <ArrowRight className="w-4 h-4" />
            </button>
          </div>
        )}
      </section>
    </div>
  );
}
