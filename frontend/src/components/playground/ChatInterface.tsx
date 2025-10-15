import React, { useState, useRef, useEffect } from 'react';
import { apiService } from '../../services/api';
import MessageContent from './MessageContent';

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
  metadataFields?: Array<{
    name: string;
    type: string;
    description: string;
  }>;
}

function ChatInterface({ appId, agentId, agentName, metadataFields }: ChatInterfaceProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputMessage, setInputMessage] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isLoadingHistory, setIsLoadingHistory] = useState(true);
  const [attachedFiles, setAttachedFiles] = useState<File[]>([]);
  const [metadataFilters, setMetadataFilters] = useState<Record<string, string>>({});
  const [isFilterExpanded, setIsFilterExpanded] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // Load conversation history on mount
  useEffect(() => {
    const loadConversationHistory = async () => {
      try {
        setIsLoadingHistory(true);
        const response = await apiService.getConversationHistory(appId, agentId);
        
        if (response.messages && response.messages.length > 0) {
          // Convert backend messages to frontend Message format
          const loadedMessages: Message[] = response.messages.map((msg: any, index: number) => ({
            id: `history-${index}`,
            type: msg.role === 'user' ? 'user' : 'agent',
            content: msg.content,
            timestamp: new Date(), // We don't have timestamp in backend, use current time
          }));
          
          setMessages(loadedMessages);
          console.log(`Loaded ${loadedMessages.length} messages from conversation history`);
        } else {
          // No history, start fresh
          setMessages([]);
        }
      } catch (error) {
        console.error('Error loading conversation history:', error);
        // Don't show error to user, just start with empty conversation
        setMessages([]);
      } finally {
        setIsLoadingHistory(false);
      }
    };

    loadConversationHistory();
  }, [appId, agentId]);

  const handleSendMessage = async () => {
    if (!inputMessage.trim() && attachedFiles.length === 0) return;

    const userMessage: Message = {
      id: Date.now().toString(),
      type: 'user',
      content: inputMessage,
      timestamp: new Date(),
      files: attachedFiles.map(f => f.name)
    };

    setMessages(prev => [...prev, userMessage]);
    setInputMessage('');
    setIsLoading(true);

    try {
      // Build metadata filter object with proper type conversion
      const filterMetadata: Record<string, any> = {};
      Object.entries(metadataFilters).forEach(([fieldName, value]) => {
        if (value.trim()) {
          // Find the field type from metadataFields
          const field = metadataFields?.find(f => f.name === fieldName);
          let convertedValue: any = value.trim();
          
          // Convert value to the appropriate type
          if (field) {
            if (field.type === 'int') {
              convertedValue = parseInt(value.trim());
            } else if (field.type === 'float') {
              convertedValue = parseFloat(value.trim());
            } else if (field.type === 'bool') {
              convertedValue = value.trim().toLowerCase() === 'true';
            }
            // For 'str' and 'date', keep as string
          }
          
          filterMetadata[fieldName] = { $eq: convertedValue };
        }
      });

      const searchParams = Object.keys(filterMetadata).length > 0 ? filterMetadata : undefined;

      const response = await apiService.chatWithAgent(
        appId,
        agentId,
        inputMessage,
        attachedFiles,
        searchParams
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
      setAttachedFiles([]); // Clear files after sending
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
      setAttachedFiles([]);
      setMetadataFilters({});
    } catch (error) {
      console.error('Error resetting conversation:', error);
    }
  };

  const handleFileUpload = (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files || []);
    setAttachedFiles(prev => [...prev, ...files]);
  };

  const handleRemoveFile = (index: number) => {
    setAttachedFiles(prev => prev.filter((_, i) => i !== index));
  };

  const handleFilterChange = (fieldName: string, value: string) => {
    setMetadataFilters(prev => ({
      ...prev,
      [fieldName]: value
    }));
  };

  const handleKeyPress = (event: React.KeyboardEvent) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      handleSendMessage();
    }
  };

  return (
    <div className="space-y-6">
      {/* Metadata Filters Section */}
      {metadataFields && metadataFields.length > 0 && (
        <div className="bg-white shadow rounded-lg">
          <div 
            className="p-4 border-b cursor-pointer hover:bg-gray-50"
            onClick={() => setIsFilterExpanded(!isFilterExpanded)}
          >
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-medium text-gray-900">
                <span className="mr-2">🔍</span>
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
            </div>
          </div>
          
          {isFilterExpanded && (
            <div className="p-4 bg-gray-50">
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {metadataFields.map((field) => (
                  <div key={field.name}>
                    <label htmlFor={`filter_${field.name}`} className="block text-sm font-medium text-gray-700 mb-1">
                      {field.name}
                      <span className="text-xs text-gray-500 ml-1">({field.type})</span>
                    </label>
                    <input
                      type="text"
                      id={`filter_${field.name}`}
                      value={metadataFilters[field.name] || ''}
                      onChange={(e) => handleFilterChange(field.name, e.target.value)}
                      placeholder={`Filter by ${field.name}`}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm"
                    />
                    {field.description && (
                      <p className="text-xs text-gray-500 mt-1">{field.description}</p>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Chat Interface */}
      <div className="bg-white shadow rounded-lg">
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
              {messages.map((message) => (
                <div
                  key={message.id}
                  className={`flex ${message.type === 'user' ? 'justify-end' : 'justify-start'}`}
                >
                  <div
                    className={`max-w-xs lg:max-w-md px-4 py-2 rounded-lg ${
                      message.type === 'user'
                        ? 'bg-blue-600 text-white'
                        : message.type === 'error'
                        ? 'bg-red-600 text-white'
                        : 'bg-gray-200 text-gray-900'
                    }`}
                  >
                    <div className="text-sm font-medium mb-1">
                      {message.type === 'user' ? 'You' : message.type === 'error' ? 'Error' : agentName}
                    </div>
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
              ))}
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
              📎 Attach Files
            </label>
          </div>

          {/* Attached Files */}
          {attachedFiles.length > 0 && (
            <div className="mb-3">
              <div className="text-sm font-medium text-gray-700 mb-2">Attached Files:</div>
              <div className="space-y-1">
                {attachedFiles.map((file, index) => (
                  <div key={index} className="flex items-center justify-between bg-white px-3 py-2 rounded border">
                    <span className="text-sm text-gray-600">{file.name}</span>
                    <button
                      onClick={() => handleRemoveFile(index)}
                      className="text-red-600 hover:text-red-800 text-sm"
                    >
                      ✕
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Message Input */}
          <div className="flex space-x-2">
            <textarea
              value={inputMessage}
              onChange={(e) => setInputMessage(e.target.value)}
              onKeyPress={handleKeyPress}
              placeholder="Type your message here... (Enter to send, Shift+Enter for new line)"
              className="flex-1 px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-none"
              rows={3}
            />
            <button
              onClick={handleSendMessage}
              disabled={isLoading || (!inputMessage.trim() && attachedFiles.length === 0)}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Send
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default ChatInterface; 