import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Gamepad2, Link2, Pencil, ArrowLeft } from 'lucide-react';
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
  source_type?: 'local' | 'a2a';
  has_memory?: boolean;
  a2a_config?: {
    remote_skill_name: string;
    health_status: string;
  } | null;
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
      const response = await apiService.getAgent(Number.parseInt(appId), Number.parseInt(agentId));
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
      const response = await apiService.createConversation(Number.parseInt(agentId));
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
    { id: 'playground', label: 'Playground', icon: <Gamepad2 className="w-4 h-4" /> },
    { id: 'api', label: 'API Examples', icon: <Link2 className="w-4 h-4" /> },
  ];

  return (
    <div className="flex flex-col gap-3 h-[calc(100vh-4rem)] animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between flex-shrink-0">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Agent Playground</h1>
        </div>
        <div className="flex items-center space-x-3">
          {agent.source_type !== 'a2a' && (
            <button
              onClick={() => setIsPromptModalOpen(true)}
              className="pg-glass px-4 py-2 rounded-lg text-indigo-600 dark:text-indigo-400 font-medium text-sm hover:bg-white/90 dark:hover:bg-gray-800/80 transition-colors flex items-center space-x-2"
            >
              <Pencil className="w-4 h-4" />
              <span>Edit Prompts</span>
            </button>
          )}
          <button
            onClick={handleBack}
            className="pg-glass px-4 py-2 rounded-lg text-gray-600 dark:text-gray-300 font-medium text-sm hover:bg-white/90 dark:hover:bg-gray-800/80 transition-colors flex items-center space-x-2"
          >
            <ArrowLeft className="w-4 h-4" />
            <span>Back to Agents</span>
          </button>
        </div>
      </div>

      {/* Agent Info — compact single-line header bar */}
      <div className="pg-glass rounded-xl px-4 py-3 flex items-center justify-between flex-shrink-0">
        <h2 className="text-base font-semibold text-gray-900 dark:text-white truncate mr-4">
          {agent.name}
        </h2>
        <div className="flex items-center gap-2 flex-shrink-0">
          <span className={`px-2.5 py-0.5 rounded-full text-xs font-medium ${
            agent.status === 'active'
              ? 'bg-green-100/80 text-green-800 dark:bg-green-900/40 dark:text-green-300'
              : 'bg-yellow-100/80 text-yellow-800 dark:bg-yellow-900/40 dark:text-yellow-300'
          }`}>
            {agent.status}
          </span>
          <span className="px-2.5 py-0.5 bg-blue-100/80 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300 rounded-full text-xs font-medium">
            {agent.type}
          </span>
          {agent.source_type === 'a2a' && (
            <span className="px-2.5 py-0.5 bg-sky-100/80 text-sky-800 dark:bg-sky-900/40 dark:text-sky-300 rounded-full text-xs font-medium">
              A2A
            </span>
          )}
          {agent.a2a_config && (
            <span className="px-2.5 py-0.5 bg-emerald-100/80 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300 rounded-full text-xs font-medium">
              {agent.a2a_config.health_status}
            </span>
          )}
          {agent.has_memory && (
            <span className="px-2.5 py-0.5 bg-purple-100/80 text-purple-800 dark:bg-purple-900/40 dark:text-purple-300 rounded-full text-xs font-medium">
              Memory
            </span>
          )}
          {agent.silo && (
            <span className="px-2.5 py-0.5 bg-teal-100/80 text-teal-800 dark:bg-teal-900/40 dark:text-teal-300 rounded-full text-xs font-medium">
              RAG
            </span>
          )}
        </div>
      </div>

      {/* Tab Navigation + Content */}
      <div className="flex flex-col flex-1 min-h-0 gap-2">
        {/* Tab bar */}
        <div className="pg-glass rounded-xl px-2 py-1.5 flex items-center gap-1 flex-shrink-0">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-all ${
                activeTab === tab.id
                  ? 'bg-white/80 dark:bg-gray-700/80 text-indigo-600 dark:text-indigo-300 border-b-2 border-indigo-500 shadow-sm'
                  : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 hover:bg-white/40 dark:hover:bg-gray-700/40'
              }`}
            >
              <span className="flex items-center gap-1.5">{tab.icon}{tab.label}</span>
            </button>
          ))}
        </div>

        {/* Tab Content */}
        <div className="flex flex-1 min-h-0 overflow-hidden rounded-xl">
          {/* Conversation Sidebar - Only show for non-OCR agents with memory */}
          {activeTab === 'playground' && !isOCRAgent && agent.has_memory && (
            <ConversationSidebar
              key={conversationReloadTrigger}
              agentId={Number.parseInt(agentId!)}
              currentConversationId={currentConversationId}
              onConversationSelect={handleConversationSelect}
              onNewConversation={handleNewConversation}
            />
          )}

          {/* Main Content Area */}
          <div className="flex-1 overflow-y-auto">
            {activeTab === 'playground' && (
              <>
                {isOCRAgent ? (
                  <OCRInterface
                    appId={Number.parseInt(appId!)}
                    agentId={Number.parseInt(agentId!)}
                    agentName={agent.name}
                    outputParser={agent.output_parser}
                  />
                ) : (
                  <ChatInterface
                    key={conversationKey}
                    appId={Number.parseInt(appId!)}
                    agentId={Number.parseInt(agentId!)}
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
                appId={Number.parseInt(appId!)}
                agentId={Number.parseInt(agentId!)}
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
        appId={Number.parseInt(appId!)}
        agentId={Number.parseInt(agentId!)}
        agentName={agent.name}
        initialSystemPrompt={agent.system_prompt || ''}
        initialPromptTemplate={agent.prompt_template || ''}
        onPromptUpdate={handlePromptUpdate}
      />
    </div>
  );
}

export default AgentPlaygroundPage; 
