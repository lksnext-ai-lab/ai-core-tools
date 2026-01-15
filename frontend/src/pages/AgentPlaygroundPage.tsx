import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { apiService } from '../services/api';
import ChatInterface from '../components/playground/ChatInterface';
import { OCRInterface } from '../components/playground/OCRInterface';
import APIExamples from '../components/playground/APIExamples';
import PromptModal from '../components/playground/PromptModal';
import ConversationSidebar from '../components/playground/ConversationSidebar';

interface Agent {
  agent_id: number;
  name: string;
  description?: string;
  status: string;
  type: string;
  has_memory?: boolean;
  system_prompt?: string;
  prompt_template?: string;
  silo?: {
    silo_id: number;
    name: string;
    vector_db_type?: string;
    metadata_definition?: {
      fields: Array<{
        name: string;
        type: string;
        description?: string;
      }>;
    };
  };
  output_parser?: {
    parser_id: number;
    name: string;
    description?: string;
    fields: Array<{
      name: string;
      type: string;
      description: string;
    }>;
  };
}

function AgentPlaygroundPage() {
  const { appId, agentId } = useParams();
  const navigate = useNavigate();
  const [agent, setAgent] = useState<Agent | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState('playground');
  const [isPromptModalOpen, setIsPromptModalOpen] = useState(false);
  const [currentConversationId, setCurrentConversationId] = useState<number | null>(null);
  const [conversationKey, setConversationKey] = useState(0); // Key to force ChatInterface remount
  const [conversationReloadTrigger, setConversationReloadTrigger] = useState(0); // Trigger to reload conversation list

  useEffect(() => {
    if (appId && agentId) {
      loadAgent();
    }
  }, [appId, agentId]);

  async function loadAgent() {
    if (!appId || !agentId) return;

    try {
      setLoading(true);
      setError(null);
      const response = await apiService.getAgent(parseInt(appId), parseInt(agentId));
      setAgent(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load agent');
      console.error('Error loading agent:', err);
    } finally {
      setLoading(false);
    }
  }

  const handlePromptUpdate = async () => {
    // Refresh agent data after prompt update
    await loadAgent();
  };

  function handleBack() {
    navigate(`/apps/${appId}/agents`);
  }

  const handleConversationSelect = (conversationId: number) => {
    setCurrentConversationId(conversationId);
    setConversationKey(prev => prev + 1); // Force remount to load new conversation
  };

  const handleNewConversation = async () => {
    if (!agentId) return;
    
    try {
      // Create a new conversation
      // Files are now managed per-conversation, so no need to clear them
      // Each conversation has its own isolated file context
      const response = await apiService.createConversation(parseInt(agentId));
      setCurrentConversationId(response.conversation_id);
      setConversationKey(prev => prev + 1); // Force remount to clear messages and load new conversation's files
      setConversationReloadTrigger(prev => prev + 1); // Trigger conversation list reload
    } catch (error) {
      console.error('Error creating new conversation:', error);
      // Fallback: just clear the current conversation
      setCurrentConversationId(null);
      setConversationKey(prev => prev + 1);
    }
  };

  const handleConversationCreated = (conversationId: number) => {
    // This is called when a conversation is auto-created during chat
    setCurrentConversationId(conversationId);
    setConversationReloadTrigger(prev => prev + 1); // Trigger conversation list reload
  };
  
  const handleMessageSent = () => {
    // This is called after sending a message to update the conversation list
    setConversationReloadTrigger(prev => prev + 1); // Trigger conversation list reload to update message counts
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="max-w-2xl mx-auto mt-8 p-6 bg-red-50 border border-red-200 rounded-lg">
        <h2 className="text-lg font-semibold text-red-800 mb-2">Error Loading Agent</h2>
        <p className="text-red-600">{error}</p>
        <button
          onClick={() => navigate(`/apps/${appId}/agents`)}
          className="mt-4 px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700"
        >
          Back to Agents
        </button>
      </div>
    );
  }

  if (!agent) {
    return (
      <div className="max-w-2xl mx-auto mt-8 p-6 bg-gray-50 border border-gray-200 rounded-lg">
        <h2 className="text-lg font-semibold text-gray-800 mb-2">Agent Not Found</h2>
        <p className="text-gray-600">The requested agent could not be found.</p>
        <button
          onClick={() => navigate(`/apps/${appId}/agents`)}
          className="mt-4 px-4 py-2 bg-gray-600 text-white rounded-lg hover:bg-gray-700"
        >
          Back to Agents
        </button>
      </div>
    );
  }

  const isOCRAgent = agent.type === 'ocr_agent';

  const tabs = [
    {
      id: 'playground',
      label: '🎮 Playground',
      description: 'Test your agent interactively'
    },
    {
      id: 'api',
      label: '🔗 API Examples',
      description: 'Integration code examples'
    }
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Agent Playground</h1>
          <p className="text-gray-600 mt-1">
            Test and integrate your AI agent
          </p>
        </div>
        <div className="flex items-center space-x-3">
          <button
            onClick={() => setIsPromptModalOpen(true)}
            className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition-colors flex items-center space-x-2"
          >
            <span>✏️</span>
            <span>Edit Prompts</span>
          </button>
          <button
            onClick={handleBack}
            className="px-4 py-2 text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50"
          >
            ← Back to Agents
          </button>
        </div>
      </div>

      {/* Agent Info */}
      <div className="bg-white shadow rounded-lg p-6">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-xl font-semibold text-gray-900">{agent.name}</h2>
            {agent.description && (
              <p className="text-gray-600 mt-1">{agent.description}</p>
            )}
          </div>
          <div className="flex items-center space-x-2">
            <span className={`px-3 py-1 rounded-full text-sm font-medium ${
              agent.status === 'active' 
                ? 'bg-green-100 text-green-800' 
                : 'bg-yellow-100 text-yellow-800'
            }`}>
              {agent.status}
            </span>
            <span className="px-3 py-1 bg-blue-100 text-blue-800 rounded-full text-sm font-medium">
              {agent.type}
            </span>
          </div>
        </div>

        {/* Silo Information */}
        {agent.silo && (
          <div className="mt-4 p-4 bg-gray-50 rounded-lg">
            <h3 className="text-sm font-medium text-gray-700 mb-2">
              <span className="mr-2">🗄️</span>
              Connected Silo: {agent.silo.name}
            </h3>
            {agent.silo.metadata_definition && (
              <p className="text-sm text-gray-600">
                <span className="mr-2">🔍</span>
                Metadata filtering available ({agent.silo.metadata_definition.fields.length} fields)
              </p>
            )}
          </div>
        )}
      </div>

      {/* Tab Navigation */}
      <div className="bg-white shadow rounded-lg">
        <div className="border-b border-gray-200">
          <nav className="-mb-px flex">
            {tabs.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`py-4 px-6 border-b-2 font-medium text-sm transition-colors ${
                  activeTab === tab.id
                    ? 'border-blue-500 text-blue-600 bg-blue-50'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                }`}
              >
                <div className="flex items-center space-x-2">
                  <span>{tab.label}</span>
                </div>
                <div className="text-xs text-gray-400 mt-1">{tab.description}</div>
              </button>
            ))}
          </nav>
        </div>

        {/* Tab Content */}
        <div className="flex flex-1 overflow-hidden">
          {/* Conversation Sidebar - Only show for non-OCR agents with memory */}
          {activeTab === 'playground' && !isOCRAgent && agent.has_memory && (
            <ConversationSidebar
              key={conversationReloadTrigger}
              agentId={parseInt(agentId!)}
              currentConversationId={currentConversationId}
              onConversationSelect={handleConversationSelect}
              onNewConversation={handleNewConversation}
            />
          )}
          
          {/* Main Content Area */}
          <div className="flex-1 p-6 overflow-y-auto">
            {activeTab === 'playground' && (
              <>
                {/* Playground Interface */}
                {isOCRAgent ? (
                  <OCRInterface 
                    appId={parseInt(appId!)} 
                    agentId={parseInt(agentId!)} 
                    agentName={agent.name}
                    outputParser={agent.output_parser}
                  />
                ) : (
                  <ChatInterface 
                    key={conversationKey}
                    appId={parseInt(appId!)} 
                    agentId={parseInt(agentId!)} 
                    agentName={agent.name}
                    conversationId={currentConversationId}
                    onConversationCreated={handleConversationCreated}
                    onMessageSent={handleMessageSent}
                    metadataFields={agent.silo?.metadata_definition?.fields}
                    vectorDbType={agent.silo?.vector_db_type}
                  />
                )}
              </>
            )}

            {activeTab === 'api' && (
              <APIExamples 
                appId={parseInt(appId!)}
                agentId={parseInt(agentId!)}
                agentName={agent.name}
                agentType={agent.type}
                hasSilo={!!agent.silo}
                siloName={agent.silo?.name}
              />
            )}
          </div>
        </div>
      </div>

      {/* Prompt Modal */}
      <PromptModal
        isOpen={isPromptModalOpen}
        onClose={() => setIsPromptModalOpen(false)}
        appId={parseInt(appId!)}
        agentId={parseInt(agentId!)}
        agentName={agent.name}
        initialSystemPrompt={agent.system_prompt || ''}
        initialPromptTemplate={agent.prompt_template || ''}
        onPromptUpdate={handlePromptUpdate}
      />
    </div>
  );
}

export default AgentPlaygroundPage; 