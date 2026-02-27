import React, { useState, useRef, useEffect, useCallback } from 'react';
import { apiService } from '../../services/api';
import MessageContent from './MessageContent';
import SearchFilters from './SearchFilters';
import type { SearchFilterMetadataField } from './SearchFilters';
import AttachedFilesPanel from './AttachedFilesPanel';
import type { PanelFile } from './AttachedFilesPanel';

interface Message {
  id: string;
  type: 'user' | 'agent' | 'error';
  content: string;
  timestamp: Date;
  files?: string[];
}

interface ChatInterfaceProps {
  appId: number;
  agentId: number;
  agentName: string;
  conversationId?: number | null;
  onConversationCreated?: (conversationId: number) => void;
  onMessageSent?: () => void;
  metadataFields?: SearchFilterMetadataField[];
  vectorDbType?: string;
}

function ChatInterface({
  appId,
  agentId,
  agentName,
  conversationId,
  onConversationCreated,
  onMessageSent,
  metadataFields,
  vectorDbType,
}: Readonly<ChatInterfaceProps>) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputMessage, setInputMessage] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isLoadingHistory, setIsLoadingHistory] = useState(true);
  const [persistentFiles, setPersistentFiles] = useState<any[]>([]);
  const [isLoadingFiles, setIsLoadingFiles] = useState(false);
  const [isFilterExpanded, setIsFilterExpanded] = useState(false);
  const [currentConversationId, setCurrentConversationId] = useState<number | null>(conversationId || null);
  const [filterMetadata, setFilterMetadata] = useState<Record<string, unknown> | undefined>(undefined);
  const [filtersKey, setFiltersKey] = useState(0);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const filterPanelId = `metadata-filters-${agentId}`;

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // Update current conversation ID when prop changes
  useEffect(() => {
    setCurrentConversationId(conversationId || null);
  }, [conversationId]);

  // Load conversation history and persistent files on mount or when conversation changes
  useEffect(() => {
    const loadConversationHistory = async () => {
      try {
        setIsLoadingHistory(true);
        
        // If we have a specific conversation ID, load from that conversation
        if (currentConversationId) {
          const response = await apiService.getConversationWithHistory(currentConversationId);
          
          if (response.messages && response.messages.length > 0) {
            const loadedMessages: Message[] = response.messages.map((msg: any, index: number) => ({
              id: `history-${index}`,
              type: msg.role === 'user' ? 'user' : 'agent',
              content: msg.content,
              timestamp: new Date(),
            }));
            
            setMessages(loadedMessages);
            console.log(`Loaded ${loadedMessages.length} messages from conversation ${currentConversationId}`);
          } else {
            setMessages([]);
          }
        } else {
          // Fallback to old method for backward compatibility
          const response = await apiService.getConversationHistory(appId, agentId);
          
          if (response.messages && response.messages.length > 0) {
            const loadedMessages: Message[] = response.messages.map((msg: any, index: number) => ({
              id: `history-${index}`,
              type: msg.role === 'user' ? 'user' : 'agent',
              content: msg.content,
              timestamp: new Date(),
            }));
            
            setMessages(loadedMessages);
            console.log(`Loaded ${loadedMessages.length} messages from conversation history`);
          } else {
            setMessages([]);
          }
        }
      } catch (error) {
        console.error('Error loading conversation history:', error);
        setMessages([]);
      } finally {
        setIsLoadingHistory(false);
      }
    };

    const loadPersistentFiles = async () => {
      try {
        // Load files for the specific conversation (if any)
        const response = await apiService.listAttachedFiles(appId, agentId, currentConversationId);
        console.log('Persistent files response:', response);
        setPersistentFiles(response.files || []);
        console.log(`Loaded ${response.files?.length || 0} persistent files for conversation ${currentConversationId}:`, response.files);
      } catch (error) {
        console.error('Error loading persistent files:', error);
        setPersistentFiles([]);
      }
    };

    loadConversationHistory();
    loadPersistentFiles();
  }, [appId, agentId, currentConversationId]);

  useEffect(() => {
    if ((!metadataFields || metadataFields.length === 0) && filterMetadata !== undefined) {
      setFilterMetadata(undefined);
      setFiltersKey((prev) => prev + 1);
    }
  }, [metadataFields, filterMetadata]);

  const handleSendMessage = async () => {
    if (!inputMessage.trim() && persistentFiles.length === 0) return;

    const userMessage: Message = {
      id: Date.now().toString(),
      type: 'user',
      content: inputMessage,
      timestamp: new Date(),
      files: persistentFiles.map(f => f.filename)
    };

    setMessages(prev => [...prev, userMessage]);
    setInputMessage('');
    setIsLoading(true);

    try {
      const hasFilters = filterMetadata !== undefined && Object.keys(filterMetadata).length > 0;
      const searchParams = hasFilters ? filterMetadata : undefined;

      // Send message (files are already attached and will be included automatically)
      const response = await apiService.chatWithAgent(
        appId,
        agentId,
        inputMessage,
        [], // No new files with message - all files are pre-uploaded
        searchParams,
        currentConversationId
      );

      // Handle both string and JSON responses
      let responseContent = response.response || 'No response received';
      
      // If response is an object, convert to formatted JSON string
      if (typeof responseContent === 'object') {
        responseContent = JSON.stringify(responseContent, null, 2);
      }
      
      const agentMessage: Message = {
        id: (Date.now() + 1).toString(),
        type: 'agent',
        content: responseContent,
        timestamp: new Date()
      };

      setMessages(prev => [...prev, agentMessage]);
      
      // If backend returned a conversation_id and we don't have one yet, use it
      if (response.conversation_id && !currentConversationId) {
        setCurrentConversationId(response.conversation_id);
        if (onConversationCreated) {
          onConversationCreated(response.conversation_id);
        }
      }
      
      // Notify parent component that a message was sent (to reload conversation list)
      if (onMessageSent) {
        onMessageSent();
      }
    } catch (error) {
      const errorMessage: Message = {
        id: (Date.now() + 1).toString(),
        type: 'error',
        content: error instanceof Error ? error.message : 'An error occurred',
        timestamp: new Date()
      };
      setMessages(prev => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleResetConversation = async () => {
    try {
      await apiService.resetAgentConversation(appId, agentId);
      setMessages([]);
      setPersistentFiles([]);
      setFilterMetadata(undefined);
      setFiltersKey((prev) => prev + 1);
    } catch (error) {
      console.error('Error resetting conversation:', error);
    }
  };

  const handleFileUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files || []);
    console.log('Uploading files:', files.map(f => f.name));
    
    setIsLoadingFiles(true);
    
    // Ensure we have a conversation to attach files to
    // This prevents files from being uploaded to a "global" session that gets lost
    let targetConversationId = currentConversationId;
    
    if (!targetConversationId) {
      try {
        // Create a conversation before uploading files
        console.log('No conversation exists, creating one for file attachment...');
        const convResponse = await apiService.createConversation(agentId);
        targetConversationId = convResponse.conversation_id;
        setCurrentConversationId(targetConversationId);
        
        // Notify parent component about the new conversation
        if (onConversationCreated) {
          onConversationCreated(targetConversationId);
        }
        console.log(`Created conversation ${targetConversationId} for file attachment`);
      } catch (convError) {
        console.error('Error creating conversation for file upload:', convError);
        setIsLoadingFiles(false);
        event.target.value = '';
        return;
      }
    }
    
    // Upload files to persistent storage, associated with the conversation
    for (const file of files) {
      try {
        const uploadResponse = await apiService.uploadFileForChat(appId, agentId, file, targetConversationId);
        console.log(`Uploaded file: ${file.name} for conversation ${targetConversationId}`, uploadResponse);
      } catch (error) {
        console.error(`Error uploading file ${file.name}:`, error);
      }
    }
    
    // Reload persistent files for current conversation
    try {
      const response = await apiService.listAttachedFiles(appId, agentId, targetConversationId);
      console.log('Reloaded persistent files:', response);
      setPersistentFiles(response.files || []);
    } catch (error) {
      console.error('Error reloading persistent files:', error);
    } finally {
      setIsLoadingFiles(false);
    }
    
    // Clear the file input
    event.target.value = '';
  };

  const handleRemovePersistentFile = async (fileId: string) => {
    try {
      await apiService.removeAttachedFile(appId, agentId, fileId, currentConversationId);
      console.log(`Removed persistent file: ${fileId} from conversation ${currentConversationId}`);
      
      // Reload persistent files for current conversation
      const response = await apiService.listAttachedFiles(appId, agentId, currentConversationId);
      setPersistentFiles(response.files || []);
    } catch (error) {
      console.error(`Error removing file ${fileId}:`, error);
    }
  };

  const handleFilterMetadataChange = useCallback((metadata: Record<string, unknown> | undefined) => {
    setFilterMetadata(metadata);
  }, []);

  const handleKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      handleSendMessage();
    }
  };

  const panelFiles: PanelFile[] = persistentFiles.map((f) => ({
    id: f.file_id,
    filename: f.filename,
    file_type: f.file_type,
    processing_status: f.processing_status,
    file_size_display: f.file_size_display,
    has_extractable_content: f.has_extractable_content,
    content_preview: f.content_preview,
  }));

  return (
    <div className="space-y-6">
      {/* Metadata Filters Section */}
      {metadataFields && metadataFields.length > 0 && (
        <div className="bg-white shadow rounded-lg">
          <button
            type="button"
            className="w-full p-4 border-b flex items-center justify-between text-left hover:bg-gray-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
            onClick={() => setIsFilterExpanded((prev) => !prev)}
            aria-expanded={isFilterExpanded}
            aria-controls={filterPanelId}
          >
            <h3 className="text-lg font-medium text-gray-900 flex items-center">
              <span className="mr-2" aria-hidden="true">🔍</span>{' '}
              Filter by Metadata
            </h3>
            <svg
              className={`w-5 h-5 text-gray-500 transform transition-transform ${isFilterExpanded ? 'rotate-180' : ''}`}
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
            </svg>
          </button>
          <div id={filterPanelId} className={`p-4 bg-gray-50 ${isFilterExpanded ? '' : 'hidden'}`}>
            <SearchFilters
              key={filtersKey}
              metadataFields={metadataFields}
              dbType={vectorDbType?.toUpperCase()}
              disabled={isLoading}
              onFilterMetadataChange={handleFilterMetadataChange}
            />
          </div>
        </div>
      )}

      {/* Chat Interface + File Panel */}
      <div className="flex gap-4 items-start">

      {/* Chat card */}
      <div className="flex-1 bg-white shadow rounded-lg">
        <div className="p-4 border-b">
          <div className="flex items-center justify-between">
            <h3 className="text-lg font-medium text-gray-900">
              <span className="mr-2">💬</span>
              Chat with {agentName}
            </h3>
            <button
              onClick={handleResetConversation}
              className="px-3 py-1 text-sm bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors"
            >
              Reset Conversation
            </button>
          </div>
        </div>

        {/* Messages Container */}
        <div className="h-96 overflow-y-auto p-4 space-y-4">
          {isLoadingHistory ? (
            <div className="flex justify-center items-center h-full">
              <div className="text-gray-500">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-gray-600 mx-auto mb-2"></div>
                Loading conversation...
              </div>
            </div>
          ) : (
            <>
              {messages.map((message) => {
                const isUserMessage = message.type === 'user';
                const isErrorMessage = message.type === 'error';
                const alignmentClass = isUserMessage ? 'justify-end' : 'justify-start';

                let bubbleClass = 'bg-gray-200 text-gray-900';
                let senderLabel = agentName;

                if (isUserMessage) {
                  bubbleClass = 'bg-blue-600 text-white';
                  senderLabel = 'You';
                } else if (isErrorMessage) {
                  bubbleClass = 'bg-red-600 text-white';
                  senderLabel = 'Error';
                }

                return (
                  <div key={message.id} className={`flex ${alignmentClass}`}>
                    <div className={`max-w-xs lg:max-w-md px-4 py-2 rounded-lg ${bubbleClass}`}>
                      <div className="text-sm font-medium mb-1">{senderLabel}</div>
                      <div>
                        <MessageContent content={message.content} />
                      </div>
                      {message.files && message.files.length > 0 && (
                        <div className="mt-2 text-xs opacity-75">
                          📎 {message.files.join(', ')}
                        </div>
                      )}
                      <div className="text-xs opacity-75 mt-1">
                        {message.timestamp.toLocaleTimeString()}
                      </div>
                    </div>
                  </div>
                );
              })}
              {isLoading && (
                <div className="flex justify-start">
                  <div className="bg-gray-200 text-gray-900 px-4 py-2 rounded-lg">
                    <div className="flex items-center">
                      <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-gray-600 mr-2"></div>
                      Thinking...
                    </div>
                  </div>
                </div>
              )}
            </>
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Input Area */}
        <div className="p-4 border-t bg-gray-50">
          {/* File Upload */}
          <div className="mb-3">
            <input
              type="file"
              multiple
              onChange={handleFileUpload}
              className="hidden"
              id="file-upload"
              accept=".pdf,.txt,.md,.png,.jpg,.jpeg,.doc,.docx"
            />
            <label
              htmlFor="file-upload"
              className="cursor-pointer inline-flex items-center px-3 py-2 border border-gray-300 rounded-lg text-sm font-medium text-gray-700 bg-white hover:bg-gray-50"
            >
              📎 Attach File
            </label>
          </div>

          {/* Message Input */}
          <div className="flex space-x-2">
            <textarea
              value={inputMessage}
              onChange={(e) => setInputMessage(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Type your message here... (Enter to send, Shift+Enter for new line)"
              className="flex-1 px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-none"
              rows={3}
            />
            <button
              onClick={handleSendMessage}
              disabled={isLoading || (!inputMessage.trim() && persistentFiles.length === 0)}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Send
            </button>
          </div>
        </div>
      </div>

      {/* Attached Files Panel */}
      <AttachedFilesPanel
        files={panelFiles}
        isLoading={isLoadingFiles}
        onRemoveFile={handleRemovePersistentFile}
      />

      </div> {/* end flex row */}
    </div>
  );
}

export default ChatInterface; 