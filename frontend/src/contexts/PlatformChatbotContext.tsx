import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import type { ReactNode } from 'react';
import { apiService } from '../services/api';
import { useUser } from './UserContext';
import { newSessionId, readHistory, resolveSessionId, writeHistory } from '../utils/platformChatbotStorage';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface PlatformChatbotConfig {
  enabled: boolean;
  agent_name: string | null;
  agent_description: string | null;
}

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  timestamp: number;
  follow_ups?: string[];
}

interface PlatformChatbotContextType {
  config: PlatformChatbotConfig | null;
  isConfigLoading: boolean;
  isOpen: boolean;
  openChat: () => void;
  closeChat: () => void;
  sessionId: string;
  messages: ChatMessage[];
  addMessage: (msg: ChatMessage) => void;
  startNewConversation: () => void;
}

// ---------------------------------------------------------------------------
// Context
// ---------------------------------------------------------------------------

const PlatformChatbotContext = createContext<PlatformChatbotContextType | undefined>(undefined);

export const usePlatformChatbot = (): PlatformChatbotContextType => {
  const context = useContext(PlatformChatbotContext);
  if (context === undefined) {
    throw new Error('usePlatformChatbot must be used within a PlatformChatbotProvider');
  }
  return context;
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const MAX_MESSAGES = 100;

// ---------------------------------------------------------------------------
// Provider
// ---------------------------------------------------------------------------

interface PlatformChatbotProviderProps {
  children: ReactNode;
}

export const PlatformChatbotProvider: React.FC<PlatformChatbotProviderProps> = ({ children }) => {
  const { user } = useUser();

  const [config, setConfig] = useState<PlatformChatbotConfig | null>(null);
  const [isConfigLoading, setIsConfigLoading] = useState(true);
  const [isOpen, setIsOpen] = useState(false);
  const [sessionId, setSessionId] = useState('');
  const [messages, setMessages] = useState<ChatMessage[]>([]);

  // Fetch config on mount
  useEffect(() => {
    let cancelled = false;
    apiService
      .getPlatformChatbotConfig()
      .then((data) => {
        if (!cancelled) setConfig(data);
      })
      .catch(() => {
        if (!cancelled) {
          setConfig({ enabled: false, agent_name: null, agent_description: null });
        }
      })
      .finally(() => {
        if (!cancelled) setIsConfigLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Initialize session ID once user is available
  useEffect(() => {
    if (!user) {
      setSessionId('');
      setMessages([]);
      return;
    }

    const resolved = resolveSessionId(user.user_id);
    setSessionId(resolved);
    setMessages(readHistory(resolved));
  }, [user]);

  const openChat = useCallback(() => setIsOpen(true), []);
  const closeChat = useCallback(() => setIsOpen(false), []);

  const addMessage = useCallback(
    (msg: ChatMessage) => {
      setMessages((prev) => {
        const next = [...prev, msg];
        const capped = next.length > MAX_MESSAGES ? next.slice(next.length - MAX_MESSAGES) : next;
        writeHistory(sessionId, capped);
        return capped;
      });
    },
    [sessionId]
  );

  const startNewConversation = useCallback(() => {
    if (!user) return;
    setSessionId(newSessionId(user.user_id));
    setMessages([]);
  }, [user]);

  return (
    <PlatformChatbotContext.Provider
      value={{
        config,
        isConfigLoading,
        isOpen,
        openChat,
        closeChat,
        sessionId,
        messages,
        addMessage,
        startNewConversation,
      }}
    >
      {children}
    </PlatformChatbotContext.Provider>
  );
};
