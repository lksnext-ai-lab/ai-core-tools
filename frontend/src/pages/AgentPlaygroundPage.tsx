import { useState, useEffect } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { Pencil, ArrowLeft } from 'lucide-react';
import { apiService } from '../services/api';
import ChatInterface from '../components/playground/ChatInterface';
import { OCRInterface } from '../components/playground/OCRInterface';
import APIExamples from '../components/playground/APIExamples';
import PromptModal from '../components/playground/PromptModal';
import ConversationSidebar from '../components/playground/ConversationSidebar';
import { LoadingState } from '../components/ui/LoadingState';
import Alert from '../components/ui/Alert';
import { ButtonApp } from '../components/ui/ButtonApp';
import { Tabs } from '../components/ui/Tabs';
import ServiceLifecycleAlert from '../components/services/ServiceLifecycleAlert';
import type { ServiceLifecycleWarning } from '../types/services';
import { Title } from '../components/ui/Title';

interface Agent {
  agent_id: number;
  name: string;
  description?: string;
  status?: string;
  type: string;
  has_memory?: boolean;
  system_prompt?: string;
  prompt_template?: string;
  lifecycle_warnings?: ServiceLifecycleWarning[];
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
      optional?: boolean;
    }>;
  };
}

function AgentPlaygroundPage() {
  const { appId, agentId } = useParams();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [agent, setAgent] = useState<Agent | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState('playground');
  const [isPromptModalOpen, setIsPromptModalOpen] = useState(false);
  const [currentConversationId, setCurrentConversationId] = useState<number | null>(() => {
    const value = searchParams.get('conversation_id');
    return value ? Number.parseInt(value, 10) : null;
  });
  const [conversationKey, setConversationKey] = useState(0); // Key to force ChatInterface remount
  const [conversationReloadTrigger, setConversationReloadTrigger] = useState(0); // Trigger to reload conversation list

  useEffect(() => {
    const value = searchParams.get('conversation_id');
    const conversationId = value ? Number.parseInt(value, 10) : null;
    if (conversationId !== currentConversationId) {
      setCurrentConversationId(conversationId);
      setConversationKey(prev => prev + 1);
    }
  }, [searchParams]);

  useEffect(() => {
    if (appId && agentId) {
      void loadAgent();
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

  const handleConversationReset = () => {
    // Conversation was deleted on the backend — clear current ID and reload sidebar
    setCurrentConversationId(null);
    setConversationKey(prev => prev + 1);
    setConversationReloadTrigger(prev => prev + 1);
  };

  if (loading) {
    return (
      <LoadingState variant="page" />
    );
  }

  if (error) {
    return (
      <Alert
        type="error"
        title="Error Loading Agent"
        className="max-w-2xl mx-auto mt-8"
        message={(
          <>
            {error}
            <span className="mt-4 block">
              <ButtonApp label="Back to Agents" variant="danger" size="medium" onClick={() => navigate(`/apps/${appId}/agents`)} />
            </span>
          </>
        )}
      />
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
    { id: 'playground', label: 'Playground' },
    { id: 'api', label: 'API Examples' },
  ];

  return (
    <div className="flex flex-col gap-3 h-[calc(100vh-4rem)] animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between flex-shrink-0">
        <Title variant="titSecundario" titulo="Agent Playground" />
        <div className="flex items-center space-x-3">
          <ButtonApp
            label="Edit Prompts"
            variant="primary"
            size="medium"
            icon={<Pencil className="w-4 h-4" />}
            onClick={() => setIsPromptModalOpen(true)}
          />
          
        </div>
      </div>

      <ServiceLifecycleAlert warnings={agent.lifecycle_warnings} variant="full" className="flex-shrink-0 max-h-48 overflow-y-auto" />

      {/* Agent Info — compact single-line header bar */}
      <div className="pg-glass rounded-xl px-4 py-3 flex items-center justify-between flex-shrink-0">
        <h2 className="text-base font-semibold text-gray-900 dark:text-white truncate mr-4">
          {agent.name}
        </h2>
        <div className="flex items-center gap-2 flex-shrink-0">
          <span className={`px-2.5 py-0.5 rounded-full text-xs font-medium ${
            agent.status !== undefined
              ? agent.status === 'active'
                ? 'bg-green-100/80 text-green-800 dark:bg-green-900/40 dark:text-green-300'
                : 'bg-yellow-100/80 text-yellow-800 dark:bg-yellow-900/40 dark:text-yellow-300'
              : ''
          }`}>
            {agent.status}
          </span>
          <span className="px-2.5 py-0.5 bg-blue-100/80 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300 rounded-full text-xs font-medium">
            {agent.type}
          </span>
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
        <Tabs tabs={tabs} activeTab={activeTab} onChange={setActiveTab} className="flex-shrink-0" />

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
          <div className="flex-1 min-h-0 overflow-y-auto">
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
                    onConversationReset={handleConversationReset}
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
