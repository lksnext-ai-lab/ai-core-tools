import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { apiService } from '../services/api';
import { LoadingState } from '../components/ui/LoadingState';
import { ErrorState } from '../components/ui/ErrorState';
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

  const [conversations, setConversations] = useState<MarketplaceConversation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState<number | null>(null);

  const handleDeleteClick = async (e: React.MouseEvent, conversationId: number) => {
    e.stopPropagation();
    if (confirmDeleteId !== conversationId) {
      setConfirmDeleteId(conversationId);
      return;
    }
    try {
      await apiService.deleteConversation(conversationId);
      setConversations((prev) => prev.filter((c) => c.conversation_id !== conversationId));
    } catch {
      // ignore
    } finally {
      setConfirmDeleteId(null);
    }
  };

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
          setError(err instanceof Error ? err.message : 'Failed to load conversations');
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

  if (loading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100 p-6">
        <LoadingState message="Loading your dashboard..." />
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100 p-6">
        <ErrorState error={error} onRetry={() => window.location.reload()} />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100 p-6">
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
            <div className="w-14 h-14 bg-blue-100 rounded-2xl flex items-center justify-center text-3xl shrink-0 group-hover:bg-blue-200 transition-colors duration-200">
              🏪
            </div>
            <div className="flex-1 min-w-0">
              <h2 className="text-xl font-semibold text-gray-900 group-hover:text-blue-700 transition-colors duration-200">
                Browse Agents
              </h2>
              <p className="text-gray-500 text-sm mt-0.5">
                Discover and chat with AI agents published by your organisation
              </p>
            </div>
            <span className="text-gray-400 text-xl group-hover:text-blue-500 transition-colors duration-200" aria-hidden="true">
              →
            </span>
          </div>
        </button>

        {/* Recent conversations */}
        <section>
          <h2 className="text-xl font-semibold text-gray-900 mb-4">My Recent Conversations</h2>

          {conversations.length === 0 ? (
            <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-10 text-center">
              <div className="w-16 h-16 bg-gray-100 rounded-full flex items-center justify-center mx-auto mb-4">
                <span className="text-3xl" aria-hidden="true">💬</span>
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
                <span className="mr-2" aria-hidden="true">🏪</span>
                Browse Agents
              </button>
            </div>
          ) : (
            <ul className="space-y-3" role="list">
              {conversations.map((conv) => (
                <li key={conv.conversation_id} className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => navigate(`/marketplace/chat/${conv.conversation_id}`)}
                    className="flex-1 min-w-0 text-left bg-white rounded-xl shadow-sm border border-gray-200 p-4 hover:border-blue-300 hover:shadow-md transition-all duration-200 group"
                  >
                    <div className="flex items-center gap-3">
                      {/* Agent icon */}
                      <div className="w-10 h-10 rounded-full bg-blue-100 flex items-center justify-center shrink-0 overflow-hidden">
                        {conv.agent_icon_url ? (
                          <img
                            src={conv.agent_icon_url}
                            alt=""
                            className="w-full h-full object-cover"
                            onError={(e) => { e.currentTarget.style.display = 'none'; }}
                          />
                        ) : (
                          <span className="text-lg" aria-hidden="true">🤖</span>
                        )}
                      </div>

                      {/* Conversation info */}
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center justify-between gap-2">
                          <span className="text-sm font-semibold text-gray-900 truncate group-hover:text-blue-700 transition-colors duration-200">
                            {conv.agent_display_name}
                          </span>
                          <time
                            dateTime={conv.updated_at}
                            className="text-xs text-gray-400 shrink-0"
                          >
                            {formatRelativeTime(conv.updated_at)}
                          </time>
                        </div>
                        {conv.last_message ? (
                          <p className="text-xs text-gray-500 truncate mt-0.5">{conv.last_message}</p>
                        ) : (
                          <p className="text-xs text-gray-400 italic mt-0.5">No messages yet</p>
                        )}
                      </div>

                      <span className="text-gray-300 group-hover:text-blue-400 transition-colors duration-200" aria-hidden="true">
                        ›
                      </span>
                    </div>
                  </button>

                  {/* Delete button */}
                  <button
                    type="button"
                    onClick={(e) => handleDeleteClick(e, conv.conversation_id)}
                    title={confirmDeleteId === conv.conversation_id ? 'Click again to confirm' : 'Delete conversation'}
                    className={`shrink-0 p-2 rounded-lg text-sm transition-colors duration-200 ${
                      confirmDeleteId === conv.conversation_id
                        ? 'bg-red-100 text-red-600 hover:bg-red-200'
                        : 'text-gray-400 hover:text-red-500 hover:bg-red-50'
                    }`}
                  >
                    {confirmDeleteId === conv.conversation_id ? '✓' : '✕'}
                  </button>
                </li>
              ))}
            </ul>
          )}

          {/* Link to full conversation list */}
          {conversations.length > 0 && (
            <div className="mt-4 text-center">
              <button
                type="button"
                onClick={() => navigate('/marketplace')}
                className="text-sm text-blue-600 hover:text-blue-800 font-medium transition-colors duration-200"
              >
                Browse more agents →
              </button>
            </div>
          )}
        </section>

      </div>
    </div>
  );
}
