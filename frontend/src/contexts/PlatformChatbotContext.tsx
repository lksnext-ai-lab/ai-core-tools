import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import type { ReactNode } from 'react';
import { apiService } from '../services/api';
import { useUser } from './UserContext';

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

const SESSION_KEY = 'platform_chatbot_session_id';
const MAX_MESSAGES = 100;

function historyKey(sessionId: string): string {
  return `platform_chatbot_history_${sessionId}`;
}

function readHistory(sessionId: string): ChatMessage[] {
  if (!sessionId) return [];
  try {
    const raw = localStorage.getItem(historyKey(sessionId));
    return raw ? (JSON.parse(raw) as ChatMessage[]) : [];
  } catch {
    return [];
  }
}

function writeHistory(sessionId: string, messages: ChatMessage[]): void {
  try {
    localStorage.setItem(historyKey(sessionId), JSON.stringify(messages));
  } catch {
    // localStorage may be unavailable or full — fail silently
  }
}

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
    if (!user) return;

    const stored = localStorage.getItem(SESSION_KEY);
    const defaultId = `platform_chatbot_${user.user_id}`;
    const resolved = stored || defaultId;

    if (!stored) {
      try {
        localStorage.setItem(SESSION_KEY, resolved);
      } catch {
        // ignore
      }
    }

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
    const newId = `platform_chatbot_${user.user_id}_${Date.now()}`;
    try {
      localStorage.setItem(SESSION_KEY, newId);
    } catch {
      // ignore
    }
    setSessionId(newId);
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
