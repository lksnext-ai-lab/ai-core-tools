import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { ArrowLeft, Bot, MessageCircle, Paperclip, Plus, Square, Mic } from 'lucide-react';
import { toast } from 'sonner';
import { apiService } from '../services/api';
import MessageContent from '../components/playground/MessageContent';
import StreamingMessage from '../components/playground/StreamingMessage';
import AudioMessage from '../components/playground/AudioMessage';
import AttachedFilesPanel from '../components/playground/AttachedFilesPanel';
import type { PanelFile } from '../components/playground/AttachedFilesPanel';
import { LoadingState } from '../components/ui/LoadingState';
import { ErrorState } from '../components/ui/ErrorState';
import { useStreamingChat, type StreamFnOptions } from '../hooks/useStreamingChat';
import { errorMessage } from '../constants/messages';

interface ChatMessage {
  readonly id: string;
  readonly type: 'user' | 'agent' | 'agent-audio' | 'error';
  readonly content: string;
  readonly timestamp: Date;
  readonly audioUrl?: string;
  readonly audioFileId?: string;
  readonly autoPlay?: boolean;
  readonly transcript?: string;
}

interface RawAttachedFile {
  readonly file_id: string;
  readonly filename: string;
  readonly file_type?: string;
  readonly processing_status?: string;
  readonly file_size_display?: string;
  readonly has_extractable_content?: boolean;
  readonly content_preview?: string;
}

interface QuotaInfo {
  readonly call_count: number;
  readonly quota: number;
  readonly is_exempt: boolean;
}

/**
 * Marketplace chat page — consumer-facing chat with the same streaming UX
 * as the playground (`ChatInterface`). Uses `useStreamingChat` bound to the
 * marketplace SSE endpoint so tool/thinking pills, token streaming, abort
 * and scroll behaviour match exactly.
 */
export default function MarketplaceChatPage() {
  const { conversationId } = useParams<{ conversationId: string }>();
  const navigate = useNavigate();
  const numericId = Number(conversationId);

  const [agentId, setAgentId] = useState<number | null>(null);
  const [agentName, _setAgentName] = useState('Agent');
  const [conversationTitle, setConversationTitle] = useState<string | null>(null);
  const [starters, setStarters] = useState<{ id: number; prompt: string }[]>([]);

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputMessage, setInputMessage] = useState('');
  const [loadingHistory, setLoadingHistory] = useState(true);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [persistentFiles, setPersistentFiles] = useState<RawAttachedFile[]>([]);
  const [isLoadingFiles, setIsLoadingFiles] = useState(false);
  const [quotaInfo, setQuotaInfo] = useState<QuotaInfo | null>(null);
  const [showScrollToBottom, setShowScrollToBottom] = useState(false);

  // Audio response
  type ResponseMode = 'text' | 'audio';
  const [responseMode, setResponseMode] = useState<ResponseMode>('text');
  const [audioLanguage, setAudioLanguage] = useState<'en' | 'es' | 'eu' | 'ca' | 'gl' | 'fr'>('en');
  const [isAudioPlaying, setIsAudioPlaying] = useState(false);
  const [isRecording, setIsRecording] = useState(false);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const audioUrlsRef = useRef<string[]>([]);

  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const lastStreamedMsgIdRef = useRef<string | null>(null);
  const userScrolledUpRef = useRef(false);
  const lastScrollTopRef = useRef(0);

  const isQuotaExceeded =
    quotaInfo !== null &&
    quotaInfo.quota > 0 &&
    !quotaInfo.is_exempt &&
    quotaInfo.call_count >= quotaInfo.quota;

  const marketplaceStream = useCallback(
    (message: string, opts: StreamFnOptions) =>
      apiService.chatMarketplaceStream(numericId, message, {
        files: opts.files,
        fileReferences: persistentFiles.length > 0 ? persistentFiles.map((f) => f.file_id) : undefined,
        responseMode: opts.responseMode,
        audioLanguage: opts.audioLanguage,
        onEvent: opts.onEvent,
        signal: opts.signal,
      }),
    [numericId, persistentFiles],
  );

  const { streamingContent, activeTools, thinkingMessage, isStreaming, sendMessage, abortStream } =
    useStreamingChat(marketplaceStream);

  const [holdStreamingContent, setHoldStreamingContent] = useState(false);
  const showStreaming = isStreaming || holdStreamingContent;

  const scrollToBottom = useCallback((behavior: ScrollBehavior = 'smooth') => {
    const container = messagesContainerRef.current;
    if (!container) return;
    container.scrollTo({ top: container.scrollHeight, behavior });
  }, []);

  const resetScrollLock = useCallback(() => {
    userScrolledUpRef.current = false;
    setShowScrollToBottom(false);
  }, []);

  useEffect(() => {
    if (!textareaRef.current) return;

    textareaRef.current.style.height = 'auto';
    textareaRef.current.style.height = `${Math.min(
      textareaRef.current.scrollHeight,
      160
    )}px`;
  }, [inputMessage]);

  useEffect(() => {
    const container = messagesContainerRef.current;
    if (!container) return;

    const threshold = 80;
    lastScrollTopRef.current = container.scrollTop;

    const handleScroll = () => {
      const { scrollTop, scrollHeight, clientHeight } = container;
      const atBottom = scrollHeight - scrollTop - clientHeight < threshold;
      const scrolledUp = scrollTop < lastScrollTopRef.current;
      lastScrollTopRef.current = scrollTop;

      if (atBottom) {
        if (userScrolledUpRef.current) {
          userScrolledUpRef.current = false;
          setShowScrollToBottom(false);
        }
        return;
      }

      if (scrolledUp && !userScrolledUpRef.current) {
        userScrolledUpRef.current = true;
        setShowScrollToBottom(true);
      }
    };

    container.addEventListener('scroll', handleScroll, { passive: true });
    return () => container.removeEventListener('scroll', handleScroll);
  }, []);

  useEffect(() => {
    if (!userScrolledUpRef.current) {
      scrollToBottom();
    }
  }, [messages, scrollToBottom]);

  useEffect(() => {
    if (isStreaming && !userScrolledUpRef.current) {
      scrollToBottom('instant');
    }
  }, [streamingContent, isStreaming, scrollToBottom]);

  const fetchQuotaInfo = useCallback(async () => {
    try {
      const data = await apiService.getMarketplaceQuotaUsage();
      setQuotaInfo(data);
    } catch {
      // Quota display is informational; failing silently is acceptable.
    }
  }, []);

  useEffect(() => {
    fetchQuotaInfo();
  }, [fetchQuotaInfo]);

  useEffect(() => {
    if (!numericId || Number.isNaN(numericId)) {
      setHistoryError('Invalid conversation ID');
      setLoadingHistory(false);
      return;
    }

    let isMounted = true;

    const loadHistory = async () => {
      setLoadingHistory(true);
      setHistoryError(null);
      setMessages([]);
      try {
        const data = await apiService.getMarketplaceConversationHistory(numericId);
        if (!isMounted) return;
        setAgentId(data.agent_id);
        setConversationTitle(data.title);

        try {
          const starters = await apiService.getAgentConversationStarters(data.agent_id);
          if (starters && starters.length > 0) {
            setStarters(starters.map((s) => ({ id: s.id, prompt: s.prompt })));
          }
        } catch {
          // Non-critical
        }


        if (data.messages && data.messages.length > 0) {
          const loaded: ChatMessage[] = await Promise.all(
            data.messages.map(
              async (msg: { role: string; content: string; message_type?: string; transcript?: string; audio_file_id?: string }, idx: number) => {
                // Handle audio messages
                if (msg.message_type === 'audio' && msg.audio_file_id) {
                  try {
                    const audioUrl = await apiService.getMarketplaceFileDownloadUrl(numericId, msg.audio_file_id);
                    audioUrlsRef.current.push(audioUrl);
                    return {
                      id: `history-${idx}`,
                      type: 'agent-audio' as const,
                      content: '',
                      transcript: msg.transcript || '',
                      audioFileId: msg.audio_file_id,
                      audioUrl,
                      autoPlay: false,
                      timestamp: new Date(),
                    };
                  } catch (err) {
                    console.error('Failed to load audio URL for message:', err);
                    // Fallback to text if audio URL can't be resolved
                    return {
                      id: `history-${idx}`,
                      type: 'agent' as const,
                      content: msg.transcript || msg.content || '',
                      timestamp: new Date(),
                    };
                  }
                }
                // Handle text messages
                return {
                  id: `history-${idx}`,
                  type: msg.role === 'user' ? ('user' as const) : ('agent' as const),
                  content: msg.content || '',
                  timestamp: new Date(),
                };
              }
            )
          );
          setMessages(loaded);
        }
      } catch (err) {
        if (!isMounted) return;
        setHistoryError(errorMessage(err, 'Failed to load conversation'));
      } finally {
        if (isMounted) setLoadingHistory(false);
      }
    };

    loadHistory();
    return () => {
      isMounted = false;
    };
  }, [numericId]);

  useEffect(() => {
    if (!numericId || Number.isNaN(numericId)) return;
    let isMounted = true;
    const loadFiles = async () => {
      try {
        const response = await apiService.listMarketplaceFiles(numericId);
        if (isMounted) setPersistentFiles(response.files || []);
      } catch {
        if (isMounted) setPersistentFiles([]);
      }
    };
    loadFiles();
    return () => {
      isMounted = false;
    };
  }, [numericId]);

  // Cleanup audio URLs on unmount
  useEffect(() => {
    return () => {
      audioUrlsRef.current.forEach((url) => URL.revokeObjectURL(url));
    };
  }, []);

  const refreshFileList = useCallback(async () => {
    try {
      const response = await apiService.listMarketplaceFiles(numericId);
      setPersistentFiles(response.files || []);
    } catch {
      // Non-critical
    }
  }, [numericId]);

  const handleStarterClick = useCallback((prompt: string) => {
    setInputMessage(prompt);
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 160)}px`;
      textareaRef.current.focus();
    }
  }, []);

  // Helper function to send a message with the given content
  const performSendMessage = useCallback(
    async (messageContent: string) => {
      if (!messageContent && persistentFiles.length === 0) return;
      if (isStreaming) return;
      if (isQuotaExceeded) return;

      const userMsg: ChatMessage = {
        id: Date.now().toString(),
        type: 'user',
        content: messageContent || `[${persistentFiles.length} file(s) attached]`,
        timestamp: new Date(),
      };

      setMessages((prev) => [...prev, userMsg]);
      setInputMessage('');
      if (textareaRef.current) {
        textareaRef.current.style.height = 'auto';
      }
      resetScrollLock();
      setTimeout(() => scrollToBottom('instant'), 50);

      try {
        setHoldStreamingContent(true);
        const result = await sendMessage(messageContent, {
          conversationId: numericId,
          responseMode,
          audioLanguage,
        });

        const rawResponse = result.response || '';
        const responseContent: string =
          typeof rawResponse === 'object'
            ? JSON.stringify(rawResponse, null, 2)
            : rawResponse;

        const agentMsgId = (Date.now() + 1).toString();
        lastStreamedMsgIdRef.current = agentMsgId;

        // Check if response is audio
        if (result.messageType === 'audio' && result.audioFileId) {
          try {
            const audioUrl = await apiService.getMarketplaceFileDownloadUrl(numericId, result.audioFileId);
            audioUrlsRef.current.push(audioUrl);

            setMessages((prev) => [
              ...prev,
              {
                id: agentMsgId,
                type: 'agent-audio',
                content: '',
                transcript: responseContent,
                audioFileId: result.audioFileId,
                audioUrl,
                autoPlay: true,
                timestamp: new Date(),
              },
            ]);
          } catch (audioError) {
            console.error('Error resolving audio file URL:', audioError);
            // Fallback to text message if audio file can't be resolved
            setMessages((prev) => [
              ...prev,
              {
                id: agentMsgId,
                type: 'agent',
                content: responseContent || 'Audio response generated but could not be retrieved.',
                timestamp: new Date(),
              },
            ]);
            toast.error('Audio response generated but could not be retrieved. Showing transcript instead.');
          }
        } else {
          setMessages((prev) => [
            ...prev,
            {
              id: agentMsgId,
              type: 'agent',
              content: responseContent,
              timestamp: new Date(),
            },
          ]);
        }

        setHoldStreamingContent(false);

        void refreshFileList();
        void fetchQuotaInfo();
      } catch (err) {
        setHoldStreamingContent(false);
        const isQuotaError =
          err instanceof Error &&
          (err.message.toLowerCase().includes('quota') ||
            err.message.toLowerCase().includes('429') ||
            err.message.toLowerCase().includes('limit'));
        const content = isQuotaError
          ? 'Marketplace call quota exceeded. Your quota resets at the start of next month.'
          : errorMessage(err, 'Failed to send message. Please try again.');
        setMessages((prev) => [
          ...prev,
          {
            id: (Date.now() + 1).toString(),
            type: 'error',
            content,
            timestamp: new Date(),
          },
        ]);
        void fetchQuotaInfo();
      }
    },
    [
      persistentFiles.length,
      isStreaming,
      isQuotaExceeded,
      sendMessage,
      numericId,
      resetScrollLock,
      scrollToBottom,
      refreshFileList,
      fetchQuotaInfo,
      responseMode,
      audioLanguage,
    ],
  );

  const handleSendMessage = useCallback(async () => {
    const trimmed = inputMessage.trim();
    performSendMessage(trimmed);
  }, [inputMessage, performSendMessage]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSendMessage();
      }
    },
    [handleSendMessage],
  );

  const handleStartRecording = async () => {
    try {
      const audioTracks = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(audioTracks);
      audioChunksRef.current = [];

      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      recorder.onstop = async () => {
        const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/webm' });
        const audioFile = new File(
          [audioBlob],
          `recording-${Date.now()}.webm`,
          {
            type: 'audio/webm',
          }
        );

        const language = audioLanguage;

        try {
          const response = await apiService.uploadRecordedAudioMarketplace(
            numericId,
            audioFile,
            language
          );
          const transcript = response.transcript;

          if (!transcript) {
            alert('No transcript available for the recording.');
            return;
          }

          // Automatically send the transcribed message
          performSendMessage(transcript);
        } catch (error) {
          console.error('Error uploading recorded audio:', error);
          toast.error('Failed to process audio. Please try again.');
        }
      };

      recorder.start();
      mediaRecorderRef.current = recorder;
      setIsRecording(true);
    } catch (error) {
      console.error('Error starting recording:', error);
      toast.error('Microphone access required to record audio.');
    }
  };

  const handleStopRecording = async () => {
    const recorder = mediaRecorderRef.current;
    if (!recorder) return;

    recorder.stop();
    recorder.stream.getTracks().forEach((track) => track.stop());
    setIsRecording(false);
  };

  // Cleanup audio URLs on unmount
  useEffect(() => {
    return () => {
      audioUrlsRef.current.forEach((url) => URL.revokeObjectURL(url));
      audioUrlsRef.current = [];
    };
  }, []);

  const handleFileSelect = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const files = e.target.files ? Array.from(e.target.files) : [];
      e.target.value = '';
      if (files.length === 0) return;

      setIsLoadingFiles(true);
      const failed: string[] = [];
      
      for (const file of files) {
        try {
          // Upload file - backend handles audio transcription if it's an audio file
          await apiService.uploadMarketplaceFile(numericId, file, audioLanguage);
        } catch (err) {
          failed.push(file.name);
          console.error(`Error uploading file ${file.name}:`, err);
        }
      }
      await refreshFileList();
      setIsLoadingFiles(false);

      if (failed.length > 0) {
        toast.error(`Failed to upload: ${failed.join(', ')}`);
      }
    },
    [numericId, refreshFileList, audioLanguage],
  );

  const resolveFileUrl = useCallback(
    (fileId: string): Promise<string> =>
      apiService.getMarketplaceFileDownloadUrl(numericId, fileId),
    [numericId],
  );

  const handleDownloadFile = useCallback(
    async (fileId: string) => {
      try {
        const url = await resolveFileUrl(fileId);
        window.open(url, '_blank');
      } catch (err) {
        toast.error(errorMessage(err, 'Failed to download file'));
      }
    },
    [resolveFileUrl],
  );

  const handleRemoveFile = useCallback(
    async (fileId: string) => {
      try {
        await apiService.removeMarketplaceFile(numericId, fileId);
        await refreshFileList();
      } catch (err) {
        toast.error(errorMessage(err, 'Failed to remove file'));
      }
    },
    [numericId, refreshFileList],
  );

  const handleNewChat = useCallback(async () => {
    if (!agentId) return;
    try {
      const conv = await apiService.createMarketplaceConversation(agentId);
      navigate(`/marketplace/chat/${conv.conversation_id ?? conv.id}`);
    } catch (err) {
      toast.error(errorMessage(err, 'Failed to create conversation'));
    }
  }, [agentId, navigate]);

  if (loadingHistory) {
    return <LoadingState message="Loading conversation..." />;
  }

  if (historyError && messages.length === 0) {
    return (
      <div className="space-y-4">
        <ErrorState error={historyError} onRetry={() => globalThis.location.reload()} />
        <div className="text-center">
          <Link
            to="/marketplace"
            className="text-sm text-blue-600 hover:text-blue-800 underline inline-flex items-center gap-1"
          >
            <ArrowLeft className="w-4 h-4" /> Back to Marketplace
          </Link>
        </div>
      </div>
    );
  }

  const panelFiles: PanelFile[] = persistentFiles.map((f) => ({
    id: f.file_id,
    filename: f.filename,
    file_type: f.file_type,
    processing_status: f.processing_status,
    file_size_display: f.file_size_display,
    has_extractable_content: f.has_extractable_content,
    content_preview: f.content_preview,
  }));

  const canSend =
    !isStreaming && !isQuotaExceeded && (inputMessage.trim().length > 0 || persistentFiles.length > 0);

  return (
    <div className="flex gap-4 items-start h-full min-h-0">
      <div className="flex-1 pg-glass rounded-2xl flex flex-col h-full min-h-[480px]">
        {/* Header */}
        <div className="flex items-center justify-between px-4 pt-3 pb-2 border-b border-white/20 dark:border-gray-700/30 flex-shrink-0">
          <div className="flex items-center gap-3 min-w-0">
            <div className="w-9 h-9 rounded-full bg-indigo-100 dark:bg-indigo-900/30 flex items-center justify-center flex-shrink-0">
              <Bot className="w-5 h-5 text-indigo-500" aria-hidden="true" />
            </div>
            <div className="min-w-0">
              <h2 className="text-sm font-semibold text-gray-900 dark:text-gray-100 truncate">
                {agentName}
              </h2>
              <p className="text-xs text-gray-500 dark:text-gray-400 truncate">
                {conversationTitle || 'New conversation'}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2 flex-shrink-0">
            {quotaInfo && quotaInfo.quota > 0 && !quotaInfo.is_exempt && (
              <span
                className={`text-xs rounded-full px-3 py-1 ${
                  isQuotaExceeded
                    ? 'bg-red-100 text-red-700 font-medium'
                    : 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300'
                }`}
              >
                {quotaInfo.call_count}/{quotaInfo.quota} Marketplace usage
              </span>
            )}
            {agentId && (
              <button
                type="button"
                onClick={handleNewChat}
                className="inline-flex items-center gap-1 text-xs font-medium px-2.5 py-1.5 rounded-lg
                           text-gray-600 dark:text-gray-300
                           hover:text-indigo-600 dark:hover:text-indigo-400
                           hover:bg-indigo-50 dark:hover:bg-indigo-900/20
                           border border-transparent hover:border-indigo-200 dark:hover:border-indigo-800/40
                           transition-all duration-150"
              >
                <Plus className="w-3.5 h-3.5" /> New chat
              </button>
            )}
            {agentId && (
              <Link
                to={`/marketplace/agents/${agentId}`}
                className="text-xs font-medium px-2.5 py-1.5 rounded-lg text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200 transition-colors"
              >
                Agent details
              </Link>
            )}
          </div>
        </div>

        {/* Messages */}
         <div
           ref={messagesContainerRef}
           className="flex-1 min-h-0 overflow-y-auto overscroll-contain px-4 py-6 space-y-6
                      bg-gradient-to-b from-gray-50/50 to-white/30
                      dark:from-gray-900/50 dark:to-gray-800/30
                      scroll-smooth"
         >
           {messages.length === 0 && !showStreaming && (
             <div className="flex flex-col items-center justify-center h-full py-12 text-center animate-fade-in">
               <div className="w-16 h-16 rounded-2xl bg-indigo-100 dark:bg-indigo-900/30 flex items-center justify-center mb-4 shadow-inner">
                 <MessageCircle
                   className="w-8 h-8 text-indigo-500"
                   aria-hidden="true"
                 />
               </div>
 
               <div className="space-y-2">
                 <p className="text-lg font-semibold text-gray-700 dark:text-gray-200">
                   Start chatting with {agentName}
                 </p>
                 <p className="text-sm text-gray-500 dark:text-gray-400 max-w-xs mx-auto">
                   Ask a question or choose a suggestion below to get started
                 </p>
               </div>

               {starters.length > 0 && (
                 <div className="mt-8 flex flex-wrap justify-center gap-3 px-4 max-w-2xl mx-auto">
                   {starters.map((starter) => (
                     <button
                       key={starter.id}
                       onClick={() => handleStarterClick(starter.prompt)}
                       className="
                         max-w-xs
                         px-4 py-2.5
                         bg-white dark:bg-gray-800
                         border border-indigo-200 dark:border-indigo-800/40
                         rounded-xl
                         text-sm text-indigo-600 dark:text-indigo-400
                         hover:bg-indigo-50 dark:hover:bg-indigo-900/30
                         hover:border-indigo-400 dark:hover:border-indigo-600
                         hover:scale-105 active:scale-95
                         transition-all duration-200 shadow-sm hover:shadow-md
                         whitespace-pre-wrap break-words
                       "
                     >
                       {starter.prompt}
                     </button>
                   ))}
                 </div>
               )}
            </div>
          )}

          {messages.map((message) => {
            if (message.type === 'user') {
              return (
                <div key={message.id} className="flex justify-end animate-slide-in-right">
                  <div className="max-w-[85%] lg:max-w-[75%]">
                    <div className="pg-bubble-user">
                      <MessageContent content={message.content} resolveFileUrl={resolveFileUrl} />
                    </div>
                    <div className="text-right mt-1">
                      <span className="text-xs text-gray-400 dark:text-gray-500">
                        {message.timestamp.toLocaleTimeString([], {
                          hour: '2-digit',
                          minute: '2-digit',
                        })}
                      </span>
                    </div>
                  </div>
                </div>
              );
            }

            if (message.type === 'error') {
              return (
                <div key={message.id} className="flex justify-start animate-slide-in-left">
                  <div className="max-w-[85%] lg:max-w-[75%]">
                    <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-700/40 text-red-700 dark:text-red-300 rounded-2xl rounded-bl-sm px-4 py-3">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-xs font-semibold uppercase tracking-wide">Error</span>
                      </div>
                      <p className="text-sm">{message.content}</p>
                    </div>
                  </div>
                </div>
              );
            }

            if (message.type === 'agent-audio') {
              const wasStreamed = message.id === lastStreamedMsgIdRef.current;
              return (
                <div
                  key={message.id}
                  className={`flex justify-start ${
                    wasStreamed ? '' : 'animate-slide-in-left'
                  }`}
                >
                  <div className="max-w-[90%] lg:max-w-[80%]">
                    <div className="pg-bubble-agent">
                      <AudioMessage
                        audioUrl={message.audioUrl!}
                        transcript={message.transcript}
                        autoPlay={message.autoPlay}
                        onPlay={() => setIsAudioPlaying(true)}
                        onPause={() => setIsAudioPlaying(false)}
                        onEnded={() => setIsAudioPlaying(false)}
                      />
                    </div>

                    <div className="mt-1">
                      <span className="text-xs text-gray-400 dark:text-gray-500">
                        {message.timestamp.toLocaleTimeString([], {
                          hour: '2-digit',
                          minute: '2-digit',
                        })}
                      </span>
                    </div>
                  </div>
                </div>
              );
            }

            const wasStreamed = message.id === lastStreamedMsgIdRef.current;
            return (
              <div
                key={message.id}
                className={`flex justify-start ${wasStreamed ? '' : 'animate-slide-in-left'}`}
              >
                <div className="max-w-[90%] lg:max-w-[80%]">
                  <div className="pg-bubble-agent text-gray-800 dark:text-gray-100">
                    <MessageContent content={message.content} resolveFileUrl={resolveFileUrl} />
                  </div>
                  <div className="mt-1">
                    <span className="text-xs text-gray-400 dark:text-gray-500">
                      {message.timestamp.toLocaleTimeString([], {
                        hour: '2-digit',
                        minute: '2-digit',
                      })}
                    </span>
                  </div>
                </div>
              </div>
            );
          })}

          {showStreaming && responseMode === 'text' && (
            <StreamingMessage
              content={streamingContent}
              isStreaming={isStreaming}
              activeTools={activeTools}
              thinkingMessage={thinkingMessage}
            />
          )}

          {showStreaming && responseMode === 'audio' && (
            <StreamingMessage
              content={''}
              isStreaming={isStreaming}
              activeTools={activeTools}
              thinkingMessage={thinkingMessage}
            />
          )}

          <div ref={messagesEndRef} />
        </div>

        {showScrollToBottom && (
          <div className="relative h-0 pointer-events-none">
            <button
              type="button"
              onClick={() => {
                resetScrollLock();
                scrollToBottom();
              }}
              className="pg-scroll-fab pointer-events-auto"
              aria-label="Scroll to bottom"
            >
              <svg
                className="w-4 h-4 text-gray-600 dark:text-gray-300"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
                aria-hidden="true"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M19 9l-7 7-7-7"
                />
              </svg>
            </button>
          </div>
        )}

        {/* Input */}
        <div className="px-4 pb-4 pt-3 border-t border-white/20 dark:border-gray-700/30 flex-shrink-0">
          {isQuotaExceeded && quotaInfo && (
            <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-700/40 rounded-lg p-3 mb-3 flex items-start gap-2">
              <span className="text-red-500 flex-shrink-0" aria-hidden="true">⚠️</span>
              <span className="text-red-600 dark:text-red-300 text-sm font-medium">
                You've reached your monthly marketplace call limit
                ({quotaInfo.call_count}/{quotaInfo.quota}).
                Your quota resets at the start of next month (UTC).
              </span>
            </div>
          )}

          {/* Response Mode & Language Controls */}
          <div className="mb-2 flex items-center gap-2 flex-wrap">
            <button
              type="button"
              onClick={() => setResponseMode('text')}
              className={`px-2 py-1 rounded-md text-xs font-medium ${responseMode === 'text' ? 'bg-indigo-600 text-white' : 'bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300'}`}
            >
              Text
            </button>
            <button
              type="button"
              onClick={() => setResponseMode('audio')}
              className={`px-2 py-1 rounded-md text-xs font-medium ${responseMode === 'audio' ? 'bg-indigo-600 text-white' : 'bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300'}`}
            >
              Audio
            </button>

            <select
              value={audioLanguage}
              onChange={(e) => setAudioLanguage(e.target.value as 'en' | 'es' | 'eu' | 'ca' | 'gl' | 'fr')}
              className="text-xs rounded-md px-2 py-1 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 text-gray-900 dark:text-gray-100"
            >
              <option value="en">EN</option>
              <option value="es">ES</option>
              <option value="ca">CA</option>
              <option value="gl">GL</option>
              <option value="eu">EU</option>
              <option value="fr">FR</option>
            </select>

            {isAudioPlaying && <span className="text-xs text-gray-500">Playing...</span>}
          </div>

           <div className="pg-glass rounded-2xl px-4 py-3 flex items-end gap-3 shadow-sm border border-white/20 dark:border-gray-700/30">
             <input
               ref={fileInputRef}
               type="file"
               multiple
               onChange={handleFileSelect}
               className="hidden"
               id="marketplace-file-upload"
               accept=".pdf,.txt,.md,.png,.jpg,.jpeg,.doc,.docx,.wav,.mp3,.ogg,.flac,.aac,.m4a,.webm"
             />
             <button
               type="button"
               onClick={() => fileInputRef.current?.click()}
               disabled={isStreaming || isQuotaExceeded}
               className="p-2 rounded-xl text-gray-400 dark:text-gray-500
                          hover:text-indigo-600 dark:hover:text-indigo-400
                          hover:bg-indigo-50 dark:hover:bg-indigo-900/20
                          disabled:opacity-40 disabled:cursor-not-allowed
                          transition-all duration-150"
               title={isQuotaExceeded ? 'Monthly quota reached' : 'Attach file'}
               aria-label="Attach file"
             >
               <Paperclip className="w-5 h-5" />
             </button>
 
             <textarea
               ref={textareaRef}
               value={inputMessage}
               onChange={(e) => setInputMessage(e.target.value)}
               onKeyDown={handleKeyDown}
               placeholder={`Message ${agentName}…`}
               disabled={isStreaming || isQuotaExceeded}
               rows={1}
               className="flex-1 bg-transparent border-none outline-none resize-none
                          text-sm text-gray-800 dark:text-gray-100
                          placeholder:text-gray-400 dark:placeholder:text-gray-500
                          disabled:opacity-50
                          focus:outline-none focus:ring-0
                          max-h-40 input-login"
               style={{ minHeight: '1.5rem' }}
             />
 
             {isStreaming ? (
               <button
                 type="button"
                 onClick={abortStream}
                 className="p-2 rounded-xl bg-red-100 dark:bg-red-900/30 text-red-600 dark:text-red-400
                            hover:bg-red-200 dark:hover:bg-red-900/50 transition-all duration-150
                            active:scale-95 shrink-0"
                 aria-label="Stop generating"
                 title="Stop generating"
               >
                 <Square className="w-4 h-4" />
               </button>
             ) : isRecording ? (
               <button
                 type="button"
                 onClick={handleStopRecording}
                 className="p-2 rounded-xl bg-red-100 dark:bg-red-900/30 text-red-600 dark:text-red-400
                            hover:bg-red-200 dark:hover:bg-red-900/50 transition-all duration-150
                            active:scale-95 shrink-0"
                 aria-label="Stop recording"
                 title="Stop recording"
               >
                 <svg
                   className="w-4 h-4"
                   fill="currentColor"
                   viewBox="0 0 24 24"
                   aria-hidden="true"
                 >
                   <rect x="6" y="6" width="12" height="12" rx="2" />
                 </svg>
               </button>
             ) : inputMessage.trim().length > 0 ? (
               <button
                 type="button"
                 onClick={handleSendMessage}
                 disabled={!canSend}
                 className="pg-btn-send shrink-0 !p-2 rounded-xl"
                 aria-label="Send message"
               >
                 <svg
                   className="w-4 h-4"
                   fill="none"
                   stroke="currentColor"
                   viewBox="0 0 24 24"
                   aria-hidden="true"
                 >
                   <path
                     strokeLinecap="round"
                     strokeLinejoin="round"
                     strokeWidth={2}
                       d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8"
                     />
                   </svg>
                 </button>
               ) : (
                 <button
                   type="button"
                   onClick={handleStartRecording}
                   className="p-2 rounded-xl bg-indigo-100 dark:bg-indigo-900/30
                             text-indigo-600 dark:text-indigo-400
                             hover:bg-indigo-200 dark:hover:bg-indigo-900/50
                             transition-all duration-150 active:scale-95 shrink-0"
                   aria-label="Record audio"
                   title="Record audio"
                 >
                   <svg
                     className="w-4 h-4"
                     fill="none"
                     stroke="currentColor"
                     viewBox="0 0 24 24"
                     aria-hidden="true"
                   >
                     <path d="M12 15a3 3 0 003-3V7a3 3 0 10-6 0v5a3 3 0 003 3z" />
                     <path d="M17 11a1 1 0 10-2 0 3 3 0 01-6 0 1 1 0 10-2 0 5 5 0 004 4.9V19H9a1 1 0 100 2h6a1 1 0 100-2h-2v-3.1A5 5 0 0017 11z" />
                   </svg>
                 </button>
               )}
           </div>

          <p className="text-xs text-gray-400 dark:text-gray-500 mt-1.5 px-1">
            Press Enter to send, Shift+Enter for new line
          </p>
        </div>
      </div>

      <AttachedFilesPanel
        files={panelFiles}
        isLoading={isLoadingFiles}
        onRemoveFile={handleRemoveFile}
        onDownloadFile={handleDownloadFile}
      />
    </div>
  );
}
