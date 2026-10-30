import { useState, useEffect } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Pencil} from 'lucide-react';
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
import { Badge } from '../components/ui/Badge';
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
  const { t } = useTranslation('common');
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
      setError(err instanceof Error ? err.message : t('agentPlayground.loadFailed'));
      console.error('Error loading agent:', err);
    } finally {
      setLoading(false);
    }
  }

  const handlePromptUpdate = async () => {
    // Refresh agent data after prompt update
    await loadAgent();
  };

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
      <div className="space-y-6">
              <div className="flex items-center justify-between">
                <Title variant="titSecundario" titulo={t('agentPlayground.title')}/>
              </div>
              <LoadingState variant="page" message={t('agentPlayground.loading')} />
            </div>
    );
  }

  if (error) {
    return (
      <Alert
        type="error"
        title={t('agentPlayground.loadErrorTitle')}
        className="max-w-2xl mx-auto mt-8"
        message={(
          <>
            {error}
            <span className="mt-4 block">
              <ButtonApp label={t('agentPlayground.backToAgents')} variant="danger" size="medium" onClick={() => navigate(`/apps/${appId}/agents`)} />
            </span>
          </>
        )}
      />
    );
  }

  if (!agent) {
    return (
      <div className="max-w-2xl mx-auto mt-8 p-6 bg-gray-50 border border-gray-200 rounded-lg">
        <h2 className="text-lg font-semibold text-gray-800 mb-2">{t('agentPlayground.notFoundTitle')}</h2>
        <p className="text-gray-600">{t('agentPlayground.notFoundMessage')}</p>
        <button
          onClick={() => navigate(`/apps/${appId}/agents`)}
          className="mt-4 px-4 py-2 bg-gray-600 text-white rounded-lg hover:bg-gray-700"
        >
          {t('agentPlayground.backToAgents')}
        </button>
      </div>
    );
  }

  const isOCRAgent = agent.type === 'ocr_agent';

  const tabs = [
    { id: 'playground', label: t('agentPlayground.tabs.playground') },
    { id: 'api', label: t('agentPlayground.tabs.apiExamples') },
  ];

  return (
    <div className="flex flex-col gap-3 h-[calc(100vh-4rem)] animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between flex-shrink-0">
        <Title
          variant="titSecundario"
          titulo={t('agentPlayground.title')}
          subtitulo={t('agentPlayground.agentSubtitle', { name: agent.name })}
          subtitleRight={(
            <div className="flex flex-wrap items-center gap-2">
              {agent.status && (
                <Badge label={agent.status} variant={agent.status === 'active' ? 'success' : 'warning'} />
              )}
              <Badge label={agent.type} variant="info" />
              {agent.has_memory && <Badge label={t('agentPlayground.memory')} variant="secondary" />}
              {agent.silo && <Badge label="RAG" variant="custom" className="bg-teal-100/80 text-teal-800 dark:bg-teal-900/40 dark:text-teal-300" />}
            </div>
          )}
        />
        <div className="flex items-center space-x-3">
          <ButtonApp
            label={t('agentPlayground.editPrompts')}
            variant="primary"
            size="medium"
            icon={<Pencil className="w-4 h-4" />}
            onClick={() => setIsPromptModalOpen(true)}
          />
          
        </div>
      </div>

      <ServiceLifecycleAlert warnings={agent.lifecycle_warnings} variant="full" className="flex-shrink-0 max-h-48 overflow-y-auto" />

      {/* Tab Navigation + Content */}
      <div className="flex flex-col flex-1 min-h-0 gap-2">
        <Tabs tabs={tabs} activeTab={activeTab} onChange={setActiveTab} className="flex-shrink-0" />

        {/* Tab Content */}
        <div className="flex flex-1 min-h-0 overflow-hidden">
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
