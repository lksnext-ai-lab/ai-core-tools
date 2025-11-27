import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { apiService } from '../services/api';
import { DEFAULT_AGENT_TEMPERATURE } from '../constants/agentConstants';
import Alert from '../components/ui/Alert';

// Define the Agent types
interface Agent {
  agent_id: number;
  name: string;
  description: string;
  system_prompt: string;
  prompt_template: string;
  type: string;
  is_tool: boolean;
  has_memory: boolean;
  memory_max_messages: number;
  memory_max_tokens: number;
  memory_summarize_threshold: number;
  service_id?: number;
  silo_id?: number;
  output_parser_id?: number;
  temperature: number;
  tool_ids?: number[];
  mcp_config_ids?: number[];
  created_at: string;
  request_count: number;
  // OCR-specific fields
  vision_service_id?: number;
  vision_system_prompt?: string;
  text_system_prompt?: string;
  ai_services: Array<{ service_id: number; name: string }>;
  silos: Array<{ silo_id: number; name: string }>;
  output_parsers: Array<{ parser_id: number; name: string }>;
  tools: Array<{ agent_id: number; name: string }>;
  mcp_configs: Array<{ config_id: number; name: string }>;
}

interface AgentFormData {
  name: string;
  description: string;
  system_prompt: string;
  prompt_template: string;
  type: string;
  is_tool: boolean;
  has_memory: boolean;
  memory_max_messages: number;
  memory_max_tokens: number;
  memory_summarize_threshold: number;
  service_id?: number;
  silo_id?: number;
  output_parser_id?: number;
  temperature: number;
  tool_ids: number[];
  mcp_config_ids: number[];
  // OCR-specific fields
  vision_service_id?: number;
  vision_system_prompt?: string;
  text_system_prompt?: string;
}

// Output Parser Field Component
const OutputParserField = ({
  showOutputParser,
  setShowOutputParser,
  formData,
  handleInputChange,
  agent
}: {
  showOutputParser: boolean;
  setShowOutputParser: (value: boolean) => void;
  formData: AgentFormData;
  handleInputChange: (field: keyof AgentFormData, value: any) => void;
  agent: Agent | null;
}) => (
  <div>
    <div className="flex items-center mb-2">
      <input
        type="checkbox"
        checked={showOutputParser}
        onChange={(e) => {
          setShowOutputParser(e.target.checked);
          if (!e.target.checked) {
            handleInputChange('output_parser_id', undefined);
          }
        }}
        className="w-5 h-5 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
      />
      <span className="ml-2 text-sm font-medium text-gray-700">Data Structure</span>
    </div>

    {showOutputParser && (
      <select
        id="output_parser"
        value={formData.output_parser_id || ''}
        onChange={(e) =>
          handleInputChange(
            'output_parser_id',
            e.target.value ? parseInt(e.target.value) : undefined
          )
        }
        className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all duration-200"
      >
        <option value="">-- Select a Data Structure --</option>
        {agent?.output_parsers.map((parser) => (
          <option key={parser.parser_id} value={parser.parser_id}>
            {parser.name}
          </option>
        ))}
      </select>
    )}
  </div>
);

function AgentFormPage() {
  const { appId, agentId } = useParams();
  const navigate = useNavigate();
  const [agent, setAgent] = useState<Agent | null>(null);
  const [loading, setLoading] = useState(true);

  // Helper function to render the "No AI Services" warning banner
  const renderNoAIServicesWarning = (isOcrAgent: boolean) => {
    const message = isOcrAgent
      ? 'You need to configure at least one AI service before creating an OCR agent. AI services define which models your agent will use for vision and text processing.'
      : 'You need to configure at least one AI service before creating an agent. AI services define which language model your agent will use.';

    return (
      <div className="mb-6 bg-amber-50 border border-amber-200 rounded-xl p-6">
        <div className="flex items-start">
          <span className="text-amber-500 text-xl mr-3">⚠️</span>
          <div className="flex-1">
            <h4 className="text-sm font-semibold text-amber-900 mb-2">No AI Services Configured</h4>
            <p className="text-sm text-amber-800 mb-3">
              {message}
            </p>
            <button
              type="button"
              onClick={() => navigate(`/apps/${appId}/settings/ai-services`)}
              className="inline-flex items-center px-4 py-2 bg-amber-600 hover:bg-amber-700 text-white text-sm font-medium rounded-lg transition-colors shadow-sm"
            >
              <span className="mr-2">⚙️</span>
              Configure AI Services
            </button>
          </div>
        </div>
      </div>
    );
  };
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [formData, setFormData] = useState<AgentFormData>({
    name: '',
    description: '',
    system_prompt: '',
    prompt_template: '',
    type: 'agent',
    is_tool: false,
    has_memory: false,
    memory_max_messages: 20,
    memory_max_tokens: 4000,
    memory_summarize_threshold: 10,
    temperature: DEFAULT_AGENT_TEMPERATURE,
    tool_ids: [],
    mcp_config_ids: []
  });
  const [showOutputParser, setShowOutputParser] = useState(false);

  // Load agent data when component mounts
  useEffect(() => {
    if (appId && agentId) {
      loadAgentData();
    } else {
      setLoading(false);
    }
  }, [appId, agentId]);

  async function loadAgentData() {
    if (!appId || !agentId) return;
    
    try {
      setLoading(true);
      setError(null);
      const response = await apiService.getAgent(parseInt(appId), parseInt(agentId));
      setAgent(response);
      
      // Initialize form data
      setFormData({
        name: response.name || '',
        description: response.description || '',
        system_prompt: response.system_prompt || '',
        prompt_template: response.prompt_template || '',
        type: response.type || 'agent',
        is_tool: response.is_tool || false,
        has_memory: response.has_memory || false,
        memory_max_messages: response.memory_max_messages || 20,
        memory_max_tokens: response.memory_max_tokens || 4000,
        memory_summarize_threshold: response.memory_summarize_threshold || 10,
        service_id: response.service_id || undefined,
        silo_id: response.silo_id || undefined,
        output_parser_id: response.output_parser_id || undefined,
        temperature: response.temperature ?? DEFAULT_AGENT_TEMPERATURE,
        tool_ids: response.tool_ids || [],
        mcp_config_ids: response.mcp_config_ids || [],
        // OCR-specific fields
        vision_service_id: response.vision_service_id || undefined,
        vision_system_prompt: response.vision_system_prompt || '',
        text_system_prompt: response.text_system_prompt || ''
      });
      
      // Set output parser toggle based on whether agent has an output parser
      setShowOutputParser(!!response.output_parser_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load agent data');
      console.error('Error loading agent data:', err);
    } finally {
      setLoading(false);
    }
  }

  const handleInputChange = (field: keyof AgentFormData, value: any) => {
    setFormData(prev => ({
      ...prev,
      [field]: value
    }));
  };

  const handleToolToggle = (toolId: number) => {
    setFormData(prev => ({
      ...prev,
      tool_ids: prev.tool_ids.includes(toolId)
        ? prev.tool_ids.filter(id => id !== toolId)
        : [...prev.tool_ids, toolId]
    }));
  };

  const handleMCPToggle = (configId: number) => {
    setFormData(prev => ({
      ...prev,
      mcp_config_ids: prev.mcp_config_ids.includes(configId)
        ? prev.mcp_config_ids.filter(id => id !== configId)
        : [...prev.mcp_config_ids, configId]
    }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!appId || !agentId) return;

    try {
      setSaving(true);
      setError(null);

      const submitData = {
        name: formData.name,
        description: formData.description,
        system_prompt: formData.system_prompt,
        prompt_template: formData.prompt_template,
        type: formData.type,
        is_tool: formData.is_tool,
        has_memory: formData.has_memory,
        memory_max_messages: formData.memory_max_messages,
        memory_max_tokens: formData.memory_max_tokens,
        memory_summarize_threshold: formData.memory_summarize_threshold,
        service_id: formData.service_id,
        silo_id: formData.silo_id,
        output_parser_id: formData.output_parser_id,
        temperature: formData.temperature,
        tool_ids: formData.tool_ids,
        mcp_config_ids: formData.mcp_config_ids,
        // OCR-specific fields
        vision_service_id: formData.vision_service_id,
        vision_system_prompt: formData.vision_system_prompt,
        text_system_prompt: formData.text_system_prompt,
        app_id: parseInt(appId)
      };

      if (parseInt(agentId) === 0) {
        // Creating new agent
        await apiService.createAgent(parseInt(appId), 0, submitData);
      } else {
        // Updating existing agent
        await apiService.updateAgent(parseInt(appId), parseInt(agentId), submitData);
      }

      // Navigate back to agents list
      navigate(`/apps/${appId}/agents`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save agent');
      console.error('Error saving agent:', err);
    } finally {
      setSaving(false);
    }
  };

  const isNewAgent = parseInt(agentId || '0') === 0;

  if (loading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100 p-6">
        <div className="flex items-center justify-center py-12">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
          <span className="ml-2 text-gray-600">Loading agent...</span>
        </div>
      </div>
    );
  }

  // Extract page title logic
  let pageTitle: string;
  if (formData.type === 'ocr_agent') {
    pageTitle = 'Agente OCR';
  } else if (isNewAgent) {
    pageTitle = 'Create Agent';
  } else {
    pageTitle = 'Edit Agent';
  }

  // Extract page description logic
  let pageDescription: string;
  if (formData.type === 'ocr_agent') {
    pageDescription = 'Configure OCR agent for document processing';
  } else if (isNewAgent) {
    pageDescription = 'Configure a new AI agent with advanced capabilities';
  } else {
    pageDescription = `Modify agent: ${agent?.name}`;
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100 p-6">
      <div className="max-w-6xl mx-auto">
        {/* Page Header */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-3xl font-bold text-gray-900">
              {pageTitle}
            </h1>
            <p className="text-gray-600 mt-2">
              {pageDescription}
            </p>
          </div>
          <button
            onClick={() => navigate(`/apps/${appId}/agents`)}
            className="flex items-center px-6 py-3 bg-white hover:bg-gray-50 rounded-xl text-gray-700 shadow-sm border border-gray-200 transition-all duration-200"
          >
            <span className="mr-2">←</span>
            {' '}Back to Agents
          </button>
        </div>

        {/* Error Message */}
        {error && (
          <Alert
            type="error"
            title="Error"
            message={error}
            className="mb-6"
            onDismiss={() => setError(null)}
          />
        )}

        {/* Agent Form */}
        <form onSubmit={handleSubmit} className="space-y-6">
          {/* Basic Information Card */}
          <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-8">
            <div className="flex items-center mb-6">
              <div className="w-10 h-10 bg-blue-100 rounded-xl flex items-center justify-center mr-4">
                <span className="text-blue-600 text-lg">📝</span>
              </div>
              <h3 className="text-xl font-semibold text-gray-900">Basic Information</h3>
            </div>
            
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div>
                <label htmlFor="name" className="block text-sm font-medium text-gray-700 mb-2">
                  Nombre *
                </label>
                <input
                  type="text"
                  id="name"
                  value={formData.name}
                  onChange={(e) => handleInputChange('name', e.target.value)}
                  className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all duration-200"
                  required
                  placeholder="Nombre..."
                />
              </div>

              <div>
                <label htmlFor="type" className="block text-sm font-medium text-gray-700 mb-2">
                  Agent Type
                </label>
                <select
                  id="type"
                  value={formData.type}
                  onChange={(e) => handleInputChange('type', e.target.value)}
                  className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all duration-200"
                >
                  <option value="agent">🤖 AI Agent</option>
                  <option value="ocr_agent">📄 OCR Agent</option>
                </select>
              </div>

              <div className="md:col-span-2">
                <label htmlFor="description" className="block text-sm font-medium text-gray-700 mb-2">
                  Descripción
                </label>
                <input
                  type="text"
                  id="description"
                  value={formData.description}
                  onChange={(e) => handleInputChange('description', e.target.value)}
                  className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all duration-200"
                  placeholder="Descripción..."
                />
              </div>
            </div>
          </div>

          {/* Agent Capabilities Card - Only for regular agents */}
          {formData.type !== 'ocr_agent' && (
            <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-8">
              <div className="flex items-center mb-6">
                <div className="w-10 h-10 bg-green-100 rounded-xl flex items-center justify-center mr-4">
                  <span className="text-green-600 text-lg">⚡</span>
                </div>
                <h3 className="text-xl font-semibold text-gray-900">Agent Capabilities</h3>
              </div>
              
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="flex items-center p-4 bg-gray-50 rounded-xl">
                  <input
                    id="is_tool"
                    type="checkbox"
                    checked={formData.is_tool}
                    onChange={(e) => handleInputChange('is_tool', e.target.checked)}
                    className="w-5 h-5 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                  />
                  <div className="ml-3">
                    <label htmlFor="is_tool" className="text-sm font-medium text-gray-900">Tool Agent</label>
                    <p className="text-xs text-gray-500">Can be used by other agents</p>
                  </div>
                </div>

                <div className="flex items-center p-4 bg-gray-50 rounded-xl">
                  <input
                    id="has_memory"
                    type="checkbox"
                    checked={formData.has_memory}
                    onChange={(e) => handleInputChange('has_memory', e.target.checked)}
                    className="w-5 h-5 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                  />
                  <div className="ml-3">
                    <label htmlFor="has_memory" className="text-sm font-medium text-gray-900">Conversational</label>
                    <p className="text-xs text-gray-500">Maintains conversation memory</p>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Memory Management Card - Only when has_memory is enabled */}
          {formData.type !== 'ocr_agent' && formData.has_memory && (
            <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-8">
              <div className="flex items-center mb-6">
                <div className="w-10 h-10 bg-indigo-100 rounded-xl flex items-center justify-center mr-4">
                  <span className="text-indigo-600 text-lg">🧠</span>
                </div>
                <div className="flex-1">
                  <h3 className="text-xl font-semibold text-gray-900">Memory Management</h3>
                  <p className="text-sm text-gray-600 mt-1">Configura la estrategia de gestión de memoria del agente</p>
                </div>
              </div>

              <div className="mb-6 p-4 bg-indigo-50 rounded-xl">
                <div className="flex items-start">
                  <span className="text-indigo-500 text-lg mr-3">ℹ️</span>
                  <div>
                    <p className="text-sm text-indigo-800 font-medium">Estrategia Híbrida Automática</p>
                    <p className="text-xs text-indigo-700 mt-1">
                      El agente aplica automáticamente una estrategia híbrida que elimina mensajes de herramientas, 
                      recorta el historial y gestiona los límites de tokens para optimizar el rendimiento y los costos.
                    </p>
                  </div>
                </div>
              </div>
              
              <div className="space-y-6">
                <div>
                  <label htmlFor="memory_max_messages" className="block text-sm font-medium text-gray-700 mb-2">
                    Máximo de Mensajes
                  </label>
                  <input
                    type="number"
                    id="memory_max_messages"
                    min="1"
                    max="100"
                    value={formData.memory_max_messages}
                    onChange={(e) => handleInputChange('memory_max_messages', parseInt(e.target.value))}
                    className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 transition-all duration-200"
                  />
                  <p className="text-xs text-gray-500 mt-2">
                    Número máximo de mensajes a mantener en el historial de conversación (recomendado: 20)
                  </p>
                </div>

                <div>
                  <label htmlFor="memory_max_tokens" className="block text-sm font-medium text-gray-700 mb-2">
                    Límite de Tokens
                  </label>
                  <input
                    type="number"
                    id="memory_max_tokens"
                    min="100"
                    max="32000"
                    step="100"
                    value={formData.memory_max_tokens}
                    onChange={(e) => handleInputChange('memory_max_tokens', parseInt(e.target.value))}
                    className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 transition-all duration-200"
                  />
                  <p className="text-xs text-gray-500 mt-2">
                    Número máximo de tokens para el historial de conversación (recomendado: 4000)
                  </p>
                </div>

                <div>
                  <label htmlFor="memory_summarize_threshold" className="block text-sm font-medium text-gray-700 mb-2">
                    Umbral de Resumen
                  </label>
                  <input
                    type="number"
                    id="memory_summarize_threshold"
                    min="1"
                    max="50"
                    value={formData.memory_summarize_threshold}
                    onChange={(e) => handleInputChange('memory_summarize_threshold', parseInt(e.target.value))}
                    className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 transition-all duration-200"
                  />
                  <p className="text-xs text-gray-500 mt-2">
                    Número de mensajes antiguos a partir del cual se considera resumir (futura implementación, recomendado: 10)
                  </p>
                </div>
              </div>

              <div className="mt-6 p-4 bg-gray-50 rounded-xl">
                <h4 className="text-sm font-semibold text-gray-900 mb-2">📊 Configuración Actual:</h4>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm">
                  <div>
                    <span className="text-gray-600">Mensajes:</span>
                    <span className="ml-2 font-medium text-gray-900">{formData.memory_max_messages}</span>
                  </div>
                  <div>
                    <span className="text-gray-600">Tokens:</span>
                    <span className="ml-2 font-medium text-gray-900">{formData.memory_max_tokens.toLocaleString()}</span>
                  </div>
                  <div>
                    <span className="text-gray-600">Umbral:</span>
                    <span className="ml-2 font-medium text-gray-900">{formData.memory_summarize_threshold}</span>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Prompts Card - Only for regular agents */}
          {formData.type !== 'ocr_agent' && (
            <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-8">
              <div className="flex items-center mb-6">
                <div className="w-10 h-10 bg-purple-100 rounded-xl flex items-center justify-center mr-4">
                  <span className="text-purple-600 text-lg">💬</span>
                </div>
                <h3 className="text-xl font-semibold text-gray-900">Prompts & Instructions</h3>
              </div>
              
              <div className="space-y-6">
                <div>
                  <label htmlFor="system_prompt" className="block text-sm font-medium text-gray-700 mb-2">
                    System Prompt
                  </label>
                  <textarea
                    id="system_prompt"
                    value={formData.system_prompt}
                    onChange={(e) => handleInputChange('system_prompt', e.target.value)}
                    rows={4}
                    className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all duration-200"
                    placeholder="Define the agent's behavior and capabilities..."
                  />
                </div>

                <div>
                  <label htmlFor="prompt_template" className="block text-sm font-medium text-gray-700 mb-2">
                    Prompt Template
                  </label>
                  <textarea
                    id="prompt_template"
                    value={formData.prompt_template}
                    onChange={(e) => handleInputChange('prompt_template', e.target.value)}
                    rows={4}
                    className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all duration-200"
                    placeholder="Template for user interactions (must include {question})..."
                  />
                  <p className="text-xs text-gray-500 mt-2">💡 The template must include {'{question}'} to work properly</p>
                </div>
              </div>
            </div>
          )}

          {/* OCR Agent Configuration Card */}
          {formData.type === 'ocr_agent' && (
            <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-8">
              <div className="flex items-center mb-6">
                <div className="w-10 h-10 bg-blue-100 rounded-xl flex items-center justify-center mr-4">
                  <span className="text-blue-600 text-lg">📄</span>
                </div>
                <h3 className="text-xl font-semibold text-gray-900">OCR Configuration</h3>
              </div>
              
              {/* No AI Services Warning */}
              {agent && agent.ai_services.length === 0 && renderNoAIServicesWarning(true)}

              <div className="space-y-6">
                <div>
                  <label htmlFor="vision_service" className="block text-sm font-medium text-gray-700 mb-2">
                    Modelo de Visión
                  </label>
                  <select
                    id="vision_service"
                    value={formData.vision_service_id || ''}
                    onChange={(e) => handleInputChange('vision_service_id', e.target.value ? parseInt(e.target.value) : undefined)}
                    className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all duration-200"
                  >
                    <option value="">-- Seleccionar modelo de visión --</option>
                    {agent?.ai_services.map((service) => (
                      <option key={service.service_id} value={service.service_id}>
                        {service.name}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label htmlFor="vision_system_prompt" className="block text-sm font-medium text-gray-700 mb-2">
                    System Prompt (Visión)
                  </label>
                  <textarea
                    id="vision_system_prompt"
                    value={formData.vision_system_prompt || ''}
                    onChange={(e) => handleInputChange('vision_system_prompt', e.target.value)}
                    rows={2}
                    className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all duration-200"
                    placeholder="Añade el system prompt para el modelo de visión..."
                  />
                </div>

                <div>
                  <label htmlFor="text_service" className="block text-sm font-medium text-gray-700 mb-2">
                    Modelo de Texto
                  </label>
                  <select
                    id="text_service"
                    value={formData.service_id || ''}
                    onChange={(e) => handleInputChange('service_id', e.target.value ? parseInt(e.target.value) : undefined)}
                    className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all duration-200"
                  >
                    <option value="">-- Seleccionar modelo de texto --</option>
                    {agent?.ai_services.map((service) => (
                      <option key={service.service_id} value={service.service_id}>
                        {service.name}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label htmlFor="text_system_prompt" className="block text-sm font-medium text-gray-700 mb-2">
                    System Prompt (Texto)
                  </label>
                  <textarea
                    id="text_system_prompt"
                    value={formData.text_system_prompt || ''}
                    onChange={(e) => handleInputChange('text_system_prompt', e.target.value)}
                    rows={2}
                    className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all duration-200"
                    placeholder="Añade el system prompt para el modelo de texto..."
                  />
                </div>

                <OutputParserField
                  showOutputParser={showOutputParser}
                  setShowOutputParser={setShowOutputParser}
                  formData={formData}
                  handleInputChange={handleInputChange}
                  agent={agent}
                />
              </div>
            </div>
          )}

          {/* Configuration Card - Only for regular agents */}
          {agent && formData.type !== 'ocr_agent' && (
            <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-8">
              <div className="flex items-center mb-6">
                <div className="w-10 h-10 bg-orange-100 rounded-xl flex items-center justify-center mr-4">
                  <span className="text-orange-600 text-lg">⚙️</span>
                </div>
                <h3 className="text-xl font-semibold text-gray-900">Configuration</h3>
              </div>
              
              {/* No AI Services Warning */}
              {agent.ai_services.length === 0 && renderNoAIServicesWarning(false)}

              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div>
                  <label htmlFor="ai_service" className="block text-sm font-medium text-gray-700 mb-2">
                    AI Service *
                  </label>
                  <select
                    id="ai_service"
                    value={formData.service_id || ''}
                    onChange={(e) => handleInputChange('service_id', e.target.value ? parseInt(e.target.value) : undefined)}
                    className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all duration-200"
                    required
                  >
                    <option value="">Select AI Service</option>
                    {agent.ai_services.map((service) => (
                      <option key={service.service_id} value={service.service_id}>
                        {service.name}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label htmlFor="silo" className="block text-sm font-medium text-gray-700 mb-2">
                    Knowledge Base (Silo)
                  </label>
                  <select
                    id="silo"
                    value={formData.silo_id || ''}
                    onChange={(e) => handleInputChange('silo_id', e.target.value ? parseInt(e.target.value) : undefined)}
                    className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all duration-200"
                  >
                    <option value="">Select Knowledge Base</option>
                    {agent.silos.map((silo) => (
                      <option key={silo.silo_id} value={silo.silo_id}>
                        {silo.name}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label htmlFor="temperature" className="block text-sm font-medium text-gray-700 mb-2">
                    Temperature
                  </label>
                  <div className="flex items-center space-x-4">
                    <input
                      type="range"
                      id="temperature"
                      min="0"
                      max="2"
                      step="0.1"
                      value={formData.temperature}
                      onChange={(e) => handleInputChange('temperature', parseFloat(e.target.value))}
                      className="flex-1 h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer"
                    />
                    <span className="text-sm font-medium text-gray-600 w-12">
                      {formData.temperature.toFixed(1)}
                    </span>
                  </div>
                  <p className="text-xs text-gray-500 mt-1">
                    Controls randomness: 0 = deterministic, 2 = very creative
                  </p>
                </div>

                <OutputParserField
                  showOutputParser={showOutputParser}
                  setShowOutputParser={setShowOutputParser}
                  formData={formData}
                  handleInputChange={handleInputChange}
                  agent={agent}
                />
              </div>
            </div>
          )}

          {/* Tools Card - Only for regular agents */}
          {agent && agent.tools.length > 0 && formData.type !== 'ocr_agent' && (
            <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-8">
              <div className="flex items-center mb-6">
                <div className="w-10 h-10 bg-yellow-100 rounded-xl flex items-center justify-center mr-4">
                  <span className="text-yellow-600 text-lg">🔧</span>
                </div>
                <h3 className="text-xl font-semibold text-gray-900">Available Tools</h3>
              </div>
              
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {agent.tools.map((tool) => (
                  <button
                    key={tool.agent_id}
                    type="button"
                    className={`p-4 rounded-xl border-2 cursor-pointer transition-all duration-200 text-left w-full ${
                      formData.tool_ids.includes(tool.agent_id)
                        ? 'border-blue-500 bg-blue-50'
                        : 'border-gray-200 bg-gray-50 hover:border-gray-300'
                    }`}
                    onClick={() => handleToolToggle(tool.agent_id)}
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center">
                        <input
                          type="checkbox"
                          checked={formData.tool_ids.includes(tool.agent_id)}
                          onChange={() => handleToolToggle(tool.agent_id)}
                          className="w-4 h-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                        />
                        <span className="ml-3 text-sm font-medium text-gray-900">{tool.name}</span>
                      </div>
                      <div className={`w-2 h-2 rounded-full ${
                        formData.tool_ids.includes(tool.agent_id) ? 'bg-blue-500' : 'bg-gray-300'
                      }`} />
                    </div>
                  </button>
                ))}
              </div>
              
              {formData.tool_ids.length > 0 && (
                <div className="mt-4 p-4 bg-blue-50 rounded-xl">
                  <p className="text-sm text-blue-800">
                    <span className="font-medium">{formData.tool_ids.length}</span> tool{formData.tool_ids.length !== 1 ? 's' : ''} selected
                  </p>
                </div>
              )}
            </div>
          )}

          {/* MCP Configs Card - Only for regular agents */}
          {agent?.mcp_configs && formData.type !== 'ocr_agent' && (
            <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-8">
              <div className="flex items-center mb-6">
                <div className="w-10 h-10 bg-purple-100 rounded-xl flex items-center justify-center mr-4">
                  <span className="text-purple-600 text-lg">🔌</span>
                </div>
                <h3 className="text-xl font-semibold text-gray-900">MCP Servers</h3>
                <div className="ml-3 px-3 py-1 bg-purple-100 text-purple-700 text-xs font-medium rounded-full">
                  Model Context Protocol
                </div>
              </div>
              
              {agent.mcp_configs.length > 0 ? (
                <>
                  <div className="mb-4 p-4 bg-purple-50 rounded-xl">
                    <div className="flex items-start">
                      <span className="text-purple-500 text-lg mr-3">ℹ️</span>
                      <div>
                        <p className="text-sm text-purple-800 font-medium">What are MCP Servers?</p>
                        <p className="text-xs text-purple-700 mt-1">
                          MCP (Model Context Protocol) servers allow agents to connect to external tools and data sources. 
                          Select the servers this agent should have access to.
                        </p>
                      </div>
                    </div>
                  </div>
                  
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    {agent.mcp_configs.map((mcp) => (
                      <button
                        key={mcp.config_id}
                        type="button"
                        className={`p-4 rounded-xl border-2 cursor-pointer transition-all duration-200 text-left w-full ${
                          formData.mcp_config_ids.includes(mcp.config_id)
                            ? 'border-purple-500 bg-purple-50'
                            : 'border-gray-200 bg-gray-50 hover:border-gray-300'
                        }`}
                        onClick={() => handleMCPToggle(mcp.config_id)}
                      >
                        <div className="flex items-center justify-between">
                          <div className="flex items-center">
                            <input
                              type="checkbox"
                              checked={formData.mcp_config_ids.includes(mcp.config_id)}
                              onChange={() => handleMCPToggle(mcp.config_id)}
                              className="w-4 h-4 rounded border-gray-300 text-purple-600 focus:ring-purple-500"
                            />
                            <span className="ml-3 text-sm font-medium text-gray-900">{mcp.name}</span>
                          </div>
                          <div className={`w-2 h-2 rounded-full ${
                            formData.mcp_config_ids.includes(mcp.config_id) ? 'bg-purple-500' : 'bg-gray-300'
                          }`} />
                        </div>
                      </button>
                    ))}
                  </div>
                  
                  {formData.mcp_config_ids.length > 0 && (
                    <div className="mt-4 p-4 bg-purple-50 rounded-xl">
                      <p className="text-sm text-purple-800">
                        <span className="font-medium">{formData.mcp_config_ids.length}</span> MCP server{formData.mcp_config_ids.length !== 1 ? 's' : ''} selected
                      </p>
                    </div>
                  )}
                </>
              ) : (
                <div className="text-center py-8">
                  <div className="w-16 h-16 bg-gray-100 rounded-full flex items-center justify-center mx-auto mb-4">
                    <span className="text-gray-400 text-2xl">🔌</span>
                  </div>
                  <h4 className="text-lg font-medium text-gray-900 mb-2">No MCP Servers Available</h4>
                  <p className="text-gray-500 mb-4">
                    You haven't configured any MCP servers yet. Create MCP configurations in the settings to enable external tool access.
                  </p>
                  <button
                    type="button"
                    onClick={() => navigate(`/apps/${appId}/settings/mcp-configs`)}
                    className="inline-flex items-center px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white text-sm font-medium rounded-lg transition-colors"
                  >
                    <span className="mr-2">⚙️</span>
                    {' '}Configure MCP Servers
                  </button>
                </div>
              )}
            </div>
          )}

          {/* Form Actions */}
          <div className="flex justify-end space-x-4 mt-8 pt-6 border-t border-gray-200">
            <button
              type="button"
              onClick={() => navigate(`/apps/${appId}/agents`)}
              className="px-8 py-3 bg-gray-100 hover:bg-gray-200 text-gray-800 rounded-xl font-medium transition-all duration-200"
              disabled={saving}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="px-8 py-3 bg-gradient-to-r from-blue-600 to-blue-700 hover:from-blue-700 hover:to-blue-800 text-white rounded-xl font-medium shadow-lg hover:shadow-xl transition-all duration-200 disabled:opacity-50"
              disabled={saving}
            >
              {(() => {
                if (saving) {
                  return (
                    <div className="flex items-center">
                      <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
                      Saving...
                    </div>
                  );
                }
                return isNewAgent ? 'Create Agent' : 'Save Changes';
              })()}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default AgentFormPage;