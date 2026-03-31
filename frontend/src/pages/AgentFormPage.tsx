import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { AlertTriangle, ArrowLeft, Settings, FileText, MessageSquare, Lightbulb, Brain, Info, BarChart2, Zap, Search, Image, Terminal, FolderSearch, Wrench, Plug, Target, Store } from 'lucide-react';
import { apiService } from '../services/api';
import { useApiMutation } from '../hooks/useApiMutation';
import { MESSAGES, errorMessage } from '../constants/messages';
import { discoverA2ACard, type AgentCard, type AgentSkill } from '../services/a2aDiscovery';
import { DEFAULT_AGENT_TEMPERATURE } from '../constants/agentConstants';
import Alert from '../components/ui/Alert';
import { TagInput } from '../components/ui/TagInput';
import { Tabs } from '../components/ui/Tabs';
import type { TabItem } from '../components/ui/Tabs';
import type { AgentMCPUsage } from '../core/types';
import type { MarketplaceVisibility, MarketplaceProfileUpdate } from '../types/marketplace';
import { MARKETPLACE_CATEGORIES } from '../types/marketplace';

type AgentSourceType = 'local' | 'a2a';

interface A2AAgentConfig {
  card_url: string;
  remote_agent_id?: string;
  remote_skill_id: string;
  remote_skill_name: string;
  remote_agent_metadata: Record<string, any>;
  remote_skill_metadata: Record<string, any>;
  sync_status: string;
  health_status: string;
  last_successful_refresh_at?: string | null;
  last_refresh_attempt_at?: string | null;
  last_refresh_error?: string | null;
  documentation_url?: string | null;
  icon_url?: string | null;
}

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
  enable_code_interpreter: boolean;
  memory_max_messages: number;
  memory_max_tokens: number;
  memory_summarize_threshold: number;
  service_id?: number;
  silo_id?: number;
  output_parser_id?: number;
  temperature: number;
  tool_ids?: number[];
  mcp_config_ids?: number[];
  skill_ids?: number[];
  created_at: string;
  request_count: number;
  marketplace_visibility?: MarketplaceVisibility;
  source_type?: AgentSourceType;
  a2a_config?: A2AAgentConfig | null;
  // OCR-specific fields
  vision_service_id?: number;
  vision_system_prompt?: string;
  text_system_prompt?: string;
  ai_services: Array<{ service_id: number; name: string }>;
  silos: Array<{ silo_id: number; name: string }>;
  output_parsers: Array<{ parser_id: number; name: string }>;
  tools: Array<{ agent_id: number; name: string }>;
  mcp_configs: Array<{ config_id: number; name: string }>;
  skills: Array<{ skill_id: number; name: string; description?: string }>;
}

interface AgentFormData {
  name: string;
  description: string;
  system_prompt: string;
  prompt_template: string;
  type: string;
  source_type: AgentSourceType;
  is_tool: boolean;
  has_memory: boolean;
  enable_code_interpreter: boolean;
  server_tools: string[];
  memory_max_messages: number;
  memory_max_tokens: number;
  memory_summarize_threshold: number;
  service_id?: number;
  silo_id?: number;
  output_parser_id?: number;
  temperature: number;
  tool_ids: number[];
  mcp_config_ids: number[];
  skill_ids: number[];
  a2a_card_url: string;
  a2a_selected_skill_id: string;
  a2a_selected_skill_name?: string;
  a2a_card_snapshot?: Record<string, any>;
  a2a_skill_snapshot?: Record<string, any>;
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
            e.target.value ? Number.parseInt(e.target.value) : undefined
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

function getPageTitle(type: string, isNewAgent: boolean): string {
  if (type === 'ocr_agent') return 'Agente OCR';
  if (isNewAgent) return 'Create Agent';
  return 'Edit Agent';
}

function getPageDescription(type: string, isNewAgent: boolean, agentName?: string): string {
  if (type === 'ocr_agent') return 'Configure OCR agent for document processing';
  if (isNewAgent) return 'Configure a new AI agent with advanced capabilities';
  return `Modify agent: ${agentName}`;
}

function AgentFormPage() {
  const { appId, agentId } = useParams();
  const navigate = useNavigate();
  const mutate = useApiMutation();
  const [agent, setAgent] = useState<Agent | null>(null);
  const [loading, setLoading] = useState(true);
  const [mcpUsage, setMcpUsage] = useState<AgentMCPUsage | null>(null);
  const [showMcpWarning, setShowMcpWarning] = useState(false);
  const [activeTab, setActiveTab] = useState<string>('basic');

  // Helper function to render the "No AI Services" warning banner
  const renderNoAIServicesWarning = (isOcrAgent: boolean) => {
    const message = isOcrAgent
      ? 'You need to configure at least one AI service before creating an OCR agent. AI services define which models your agent will use for vision and text processing.'
      : 'You need to configure at least one AI service before creating an agent. AI services define which language model your agent will use.';

    return (
      <div className="mb-6 bg-amber-50 border border-amber-200 rounded-xl p-6">
        <div className="flex items-start">
          <AlertTriangle className="w-5 h-5 text-amber-500 mr-3 shrink-0" />
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
              <Settings className="w-4 h-4 mr-2" />
              {' '}
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
    source_type: 'local',
    is_tool: false,
    has_memory: false,
    enable_code_interpreter: false,
    server_tools: [],
    memory_max_messages: 20,
    memory_max_tokens: 4000,
    memory_summarize_threshold: 4000,
    temperature: DEFAULT_AGENT_TEMPERATURE,
    tool_ids: [],
    mcp_config_ids: [],
    skill_ids: [],
    a2a_card_url: '',
    a2a_selected_skill_id: ''
  });
  const [showOutputParser, setShowOutputParser] = useState(false);
  const [a2aDiscovery, setA2aDiscovery] = useState<{ card: AgentCard; skills: AgentSkill[] } | null>(null);
  const [a2aLoading, setA2aLoading] = useState(false);
  const [a2aError, setA2aError] = useState<string | null>(null);

  // Marketplace state
  const [showMarketplace, setShowMarketplace] = useState(false);
  const [marketplaceVisibility, setMarketplaceVisibility] = useState<MarketplaceVisibility>('unpublished');
  const [marketplaceProfile, setMarketplaceProfile] = useState<MarketplaceProfileUpdate>({
    display_name: null,
    short_description: null,
    long_description: null,
    category: null,
    tags: null,
    icon_url: null,
    cover_image_url: null,
  });
  const [savingMarketplace, setSavingMarketplace] = useState(false);
  const [marketplaceSuccess, setMarketplaceSuccess] = useState<string | null>(null);

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
      const response = await apiService.getAgent(Number.parseInt(appId), Number.parseInt(agentId));
      setAgent(response);

      // Initialize form data
      setFormData({
        name: response.name || '',
        description: response.description || '',
        system_prompt: response.system_prompt || '',
        prompt_template: response.prompt_template || '',
        type: response.type || 'agent',
        source_type: response.source_type || 'local',
        is_tool: response.is_tool || false,
        has_memory: response.has_memory || false,
        enable_code_interpreter: response.enable_code_interpreter || false,
        server_tools: response.server_tools || [],
        memory_max_messages: response.memory_max_messages || 20,
        memory_max_tokens: response.memory_max_tokens || 4000,
        memory_summarize_threshold: response.memory_summarize_threshold || 4000,
        service_id: response.service_id || undefined,
        silo_id: response.silo_id || undefined,
        output_parser_id: response.output_parser_id || undefined,
        temperature: response.temperature ?? DEFAULT_AGENT_TEMPERATURE,
        tool_ids: response.tool_ids || [],
        mcp_config_ids: response.mcp_config_ids || [],
        skill_ids: response.skill_ids || [],
        a2a_card_url: response.a2a_config?.card_url || '',
        a2a_selected_skill_id: response.a2a_config?.remote_skill_id || '',
        a2a_selected_skill_name: response.a2a_config?.remote_skill_name || '',
        a2a_card_snapshot: response.a2a_config?.remote_agent_metadata || undefined,
        a2a_skill_snapshot: response.a2a_config?.remote_skill_metadata || undefined,
        // OCR-specific fields
        vision_service_id: response.vision_service_id || undefined,
        vision_system_prompt: response.vision_system_prompt || '',
        text_system_prompt: response.text_system_prompt || ''
      });

      if (response.a2a_config?.remote_agent_metadata) {
        const remoteCard = response.a2a_config.remote_agent_metadata as AgentCard;
        const remoteSkills = Array.isArray(remoteCard.skills) ? remoteCard.skills : [];
        setA2aDiscovery({ card: remoteCard, skills: remoteSkills });
      } else {
        setA2aDiscovery(null);
      }

      // Set output parser toggle based on whether agent has an output parser
      setShowOutputParser(!!response.output_parser_id);

      // Load MCP usage and marketplace profile for existing agents
      if (Number.parseInt(agentId) !== 0) {
        try {
          const usage = await apiService.getAgentMCPUsage(Number.parseInt(appId), Number.parseInt(agentId));
          setMcpUsage(usage);
        } catch (usageErr) {
          console.error('Error loading MCP usage:', usageErr);
        }

        try {
          const profile = await apiService.getAgentMarketplaceProfile(Number.parseInt(appId), Number.parseInt(agentId));
          setMarketplaceProfile({
            display_name: profile.display_name || null,
            short_description: profile.short_description || null,
            long_description: profile.long_description || null,
            category: profile.category || null,
            tags: profile.tags || null,
            icon_url: profile.icon_url || null,
            cover_image_url: profile.cover_image_url || null,
          });
        } catch {
          // Profile may not exist yet — that's fine
        }

        // Marketplace visibility comes from agent detail
        if (response.marketplace_visibility) {
          setMarketplaceVisibility(response.marketplace_visibility as MarketplaceVisibility);
          setShowMarketplace(response.marketplace_visibility !== 'unpublished');
        }
      }
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

  const handleSkillToggle = (skillId: number) => {
    setFormData(prev => ({
      ...prev,
      skill_ids: prev.skill_ids.includes(skillId)
        ? prev.skill_ids.filter(id => id !== skillId)
        : [...prev.skill_ids, skillId]
    }));
  };

  const applyImportedA2ASkill = useCallback((card: AgentCard, skill: AgentSkill) => {
    setFormData(prev => ({
      ...prev,
      source_type: 'a2a',
      type: 'agent',
      name: skill.name || card.name || prev.name,
      description: skill.description || card.description || prev.description,
      has_memory: false,
      enable_code_interpreter: false,
      server_tools: [],
      service_id: undefined,
      silo_id: undefined,
      output_parser_id: undefined,
      tool_ids: [],
      mcp_config_ids: [],
      skill_ids: [],
      system_prompt: '',
      prompt_template: '',
      a2a_selected_skill_id: skill.id,
      a2a_selected_skill_name: skill.name,
      a2a_card_snapshot: card as Record<string, any>,
      a2a_skill_snapshot: skill as Record<string, any>,
    }));
    setShowOutputParser(false);
  }, []);

  const handleSourceTypeChange = (sourceType: AgentSourceType) => {
    setA2aError(null);
    if (sourceType === 'local') {
      setA2aDiscovery(null);
      setFormData(prev => ({
        ...prev,
        source_type: 'local',
        a2a_selected_skill_id: '',
        a2a_selected_skill_name: undefined,
        a2a_card_snapshot: undefined,
        a2a_skill_snapshot: undefined,
      }));
      return;
    }

    setFormData(prev => ({
      ...prev,
      source_type: 'a2a',
      type: 'agent',
      has_memory: false,
      enable_code_interpreter: false,
      server_tools: [],
      service_id: undefined,
      silo_id: undefined,
      output_parser_id: undefined,
      tool_ids: [],
      mcp_config_ids: [],
      skill_ids: [],
      system_prompt: '',
      prompt_template: '',
    }));
    setShowOutputParser(false);
  };

  const handleDiscoverA2AAgent = useCallback(async () => {
    if (!appId) {
      setA2aError('Missing app context while loading the A2A agent card.');
      return;
    }

    if (!formData.a2a_card_url.trim()) {
      setA2aError('Enter a public A2A agent card URL first.');
      return;
    }

    try {
      setA2aLoading(true);
      setA2aError(null);
      const discovery = await discoverA2ACard(Number.parseInt(appId), formData.a2a_card_url.trim());
      setA2aDiscovery({ card: discovery.card, skills: discovery.skills });

      if (discovery.skills.length === 0) {
        setA2aError('This A2A agent card does not expose any importable skills.');
        setFormData(prev => ({
          ...prev,
          a2a_selected_skill_id: '',
          a2a_selected_skill_name: undefined,
          a2a_card_snapshot: discovery.card as Record<string, any>,
          a2a_skill_snapshot: undefined,
        }));
        return;
      }

      const selectedSkill =
        discovery.skills.find((skill) => skill.id === formData.a2a_selected_skill_id) ||
        discovery.skills[0];

      applyImportedA2ASkill(discovery.card, selectedSkill);
    } catch (err) {
      setA2aDiscovery(null);
      setA2aError(err instanceof Error ? err.message : 'Failed to load the A2A agent card');
    } finally {
      setA2aLoading(false);
    }
  }, [appId, applyImportedA2ASkill, formData.a2a_card_url, formData.a2a_selected_skill_id]);

  const handleA2ASkillSelect = (skillId: string) => {
    if (!a2aDiscovery) return;
    const selectedSkill = a2aDiscovery.skills.find((skill) => skill.id === skillId);
    if (!selectedSkill) return;
    applyImportedA2ASkill(a2aDiscovery.card, selectedSkill);
  };

  // Marketplace handlers
  const handleVisibilityChange = useCallback(async (visibility: MarketplaceVisibility) => {
    if (!appId || !agentId || Number.parseInt(agentId) === 0) return;
    const previous = marketplaceVisibility;
    setMarketplaceVisibility(visibility);
    setShowMarketplace(visibility !== 'unpublished');
    try {
      await apiService.updateAgentMarketplaceVisibility(
        Number.parseInt(appId),
        Number.parseInt(agentId),
        visibility,
      );
    } catch (err) {
      // Revert to previous value on failure to avoid UI/server desync
      setMarketplaceVisibility(previous);
      setShowMarketplace(previous !== 'unpublished');
      console.error('Error updating marketplace visibility:', err);
      setError(err instanceof Error ? err.message : 'Failed to update visibility');
    }
  }, [appId, agentId, marketplaceVisibility]);

  const handleMarketplaceProfileChange = useCallback(
    (field: keyof MarketplaceProfileUpdate, value: string | string[] | null) => {
      setMarketplaceProfile(prev => ({ ...prev, [field]: value }));
      setMarketplaceSuccess(null);
    },
    [],
  );

  const handleSaveMarketplaceProfile = useCallback(async () => {
    if (!appId || !agentId || Number.parseInt(agentId) === 0) return;

    setSavingMarketplace(true);
    setMarketplaceSuccess(null);
    const saved = await mutate(
      () =>
        apiService.updateAgentMarketplaceProfile(
          Number.parseInt(appId),
          Number.parseInt(agentId),
          marketplaceProfile,
        ),
      {
        loading: MESSAGES.SAVING('marketplace profile'),
        success: 'Marketplace profile saved',
        error: (err) => errorMessage(err, MESSAGES.SAVE_FAILED('marketplace profile')),
      },
    );
    setSavingMarketplace(false);

    if (saved === undefined) return;

    setMarketplaceProfile({
      display_name: saved.display_name || null,
      short_description: saved.short_description || null,
      long_description: saved.long_description || null,
      category: saved.category || null,
      tags: saved.tags || null,
      icon_url: saved.icon_url || null,
      cover_image_url: saved.cover_image_url || null,
    });
    setMarketplaceSuccess('Marketplace profile saved successfully');
  }, [appId, agentId, marketplaceProfile, mutate]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!appId || !agentId) return;

    const submitData = {
      name: formData.name,
      description: formData.description,
      system_prompt: formData.system_prompt,
      prompt_template: formData.prompt_template,
      type: formData.type,
        source_type: formData.source_type,
      is_tool: formData.is_tool,
      has_memory: formData.has_memory,
      enable_code_interpreter: formData.enable_code_interpreter,
      server_tools: formData.server_tools,
      memory_max_messages: formData.memory_max_messages,
      memory_max_tokens: formData.memory_max_tokens,
      memory_summarize_threshold: formData.memory_summarize_threshold,
      service_id: formData.service_id,
      silo_id: formData.silo_id,
      output_parser_id: formData.output_parser_id,
      temperature: formData.temperature,
      tool_ids: formData.tool_ids,
      mcp_config_ids: formData.mcp_config_ids,
      skill_ids: formData.skill_ids,
      // OCR-specific fields
      vision_service_id: formData.vision_service_id,
      vision_system_prompt: formData.vision_system_prompt,
      text_system_prompt: formData.text_system_prompt,
        a2a_config: formData.source_type === 'a2a' ? {
          card_url: formData.a2a_card_url,
          selected_skill_id: formData.a2a_selected_skill_id,
          selected_skill_name: formData.a2a_selected_skill_name,
          card_snapshot: formData.a2a_card_snapshot,
          skill_snapshot: formData.a2a_skill_snapshot,
        } : undefined,
      app_id: Number.parseInt(appId),
    };

      if (formData.source_type === 'a2a') {
        if (!formData.a2a_card_url || !formData.a2a_selected_skill_id) {
          throw new Error('Load a public A2A agent card and select a skill before saving.');
        }
      }

    const isNew = Number.parseInt(agentId) === 0;

    setError(null);
    setSaving(true);
    const result = await mutate(
      () =>
        isNew
          ? apiService.createAgent(Number.parseInt(appId), 0, submitData)
          : apiService.updateAgent(Number.parseInt(appId), Number.parseInt(agentId), submitData),
      {
        loading: isNew ? MESSAGES.CREATING('agent') : MESSAGES.UPDATING('agent'),
        success: isNew ? MESSAGES.CREATED('agent') : MESSAGES.UPDATED('agent'),
        error: (err) => errorMessage(err, MESSAGES.SAVE_FAILED('agent')),
      },
    );
    setSaving(false);

    if (result !== undefined) {
      navigate(`/apps/${appId}/agents`);
    }
  };

  const isNewAgent = Number.parseInt(agentId || '0') === 0;

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

  const pageTitle = getPageTitle(formData.type, isNewAgent);
  const pageDescription = getPageDescription(formData.type, isNewAgent, agent?.name);
  const isA2AAgent = formData.source_type === 'a2a';

  const tabs: TabItem[] = [
    { id: 'basic', label: 'Basic' },
    { id: 'prompts', label: 'Prompts' },
    { id: 'configuration', label: 'Configuration' },
    { id: 'advanced', label: 'Advanced' },
    { id: 'marketplace', label: 'Marketplace' }
  ];

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
            <ArrowLeft className="w-4 h-4 mr-2" />
            {' '}
            Back to Agents
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
          {/* Tab Navigation */}
          <Tabs
            tabs={tabs}
            activeTab={activeTab}
            onChange={setActiveTab}
          />

          {/* TAB 1: BASIC */}
          {activeTab === 'basic' && (
            <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-8">
              <div className="flex items-center mb-6">
                <div className="w-10 h-10 bg-blue-100 rounded-xl flex items-center justify-center mr-4">
                  <FileText className="w-5 h-5 text-blue-600" />
                </div>
                <h3 className="text-xl font-semibold text-gray-900">Basic Information</h3>
              </div>
              
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div>
                  <label htmlFor="source_type" className="block text-sm font-medium text-gray-700 mb-2">
                    Source
                  </label>
                  <select
                    id="source_type"
                    value={formData.source_type}
                    onChange={(e) => handleSourceTypeChange(e.target.value as AgentSourceType)}
                    disabled={!isNewAgent}
                    className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all duration-200 disabled:bg-gray-100 disabled:text-gray-500"
                  >
                    <option value="local">Local</option>
                    <option value="a2a">External / A2A Agent</option>
                  </select>
                </div>

                <div>
                  <label htmlFor="type" className="block text-sm font-medium text-gray-700 mb-2">
                    Agent Type
                  </label>
                  <select
                    id="type"
                    value={formData.type}
                    onChange={(e) => handleInputChange('type', e.target.value)}
                    disabled={isA2AAgent}
                    className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all duration-200 disabled:bg-gray-100 disabled:text-gray-500"
                  >
                    <option value="agent">AI Agent</option>
                    <option value="ocr_agent">OCR Agent</option>
                  </select>
                </div>

                {isA2AAgent && (
                  <div className="md:col-span-2 rounded-2xl border border-blue-200 bg-blue-50 p-6">
                    <div className="flex items-start justify-between gap-4">
                      <div>
                        <h4 className="text-sm font-semibold text-blue-900">Import Public A2A Agent</h4>
                        <p className="mt-1 text-sm text-blue-800">
                          Load a public agent card through the backend, choose exactly one remote skill, and create a first-class MattinAI agent backed by that external capability.
                        </p>
                      </div>
                      <button
                        type="button"
                        onClick={() => { void handleDiscoverA2AAgent(); }}
                        disabled={a2aLoading}
                        className="shrink-0 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-blue-300"
                      >
                        {a2aLoading ? 'Loading...' : 'Load Card'}
                      </button>
                    </div>

                    <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2">
                      <div className="md:col-span-2">
                        <label htmlFor="a2a_card_url" className="block text-sm font-medium text-blue-900 mb-2">
                          Public Agent Card URL
                        </label>
                        <input
                          type="url"
                          id="a2a_card_url"
                          value={formData.a2a_card_url}
                          onChange={(e) => handleInputChange('a2a_card_url', e.target.value)}
                          className="w-full rounded-xl border border-blue-200 bg-white px-4 py-3 focus:border-blue-500 focus:ring-2 focus:ring-blue-500"
                          placeholder="https://example.com/.well-known/agent-card.json"
                        />
                      </div>

                      {a2aDiscovery && (
                        <>
                          <div>
                            <label htmlFor="a2a_skill" className="block text-sm font-medium text-blue-900 mb-2">
                              Remote Skill
                            </label>
                            <select
                              id="a2a_skill"
                              value={formData.a2a_selected_skill_id}
                              onChange={(e) => handleA2ASkillSelect(e.target.value)}
                              className="w-full rounded-xl border border-blue-200 bg-white px-4 py-3 focus:border-blue-500 focus:ring-2 focus:ring-blue-500"
                            >
                              {a2aDiscovery.skills.map((skill) => (
                                <option key={skill.id} value={skill.id}>
                                  {skill.name}
                                </option>
                              ))}
                            </select>
                          </div>

                          <div className="rounded-xl border border-blue-200 bg-white p-4">
                            <p className="text-xs font-semibold uppercase tracking-wide text-blue-700">Remote Agent</p>
                            <p className="mt-1 text-sm font-semibold text-gray-900">{a2aDiscovery.card.name}</p>
                            {a2aDiscovery.card.description && (
                              <p className="mt-2 text-sm text-gray-600">{a2aDiscovery.card.description}</p>
                            )}
                            <div className="mt-3 flex flex-wrap gap-2 text-xs">
                              <span className="rounded-full bg-blue-100 px-2 py-1 font-medium text-blue-800">
                                {a2aDiscovery.skills.length} skill{a2aDiscovery.skills.length === 1 ? '' : 's'}
                              </span>
                              <span className="rounded-full bg-emerald-100 px-2 py-1 font-medium text-emerald-800">
                                Browser discovery OK
                              </span>
                            </div>
                          </div>
                        </>
                      )}
                    </div>

                    {a2aError && (
                      <p className="mt-3 text-sm text-red-700">{a2aError}</p>
                    )}

                    {agent?.a2a_config && (
                      <div className="mt-4 rounded-xl border border-gray-200 bg-white p-4 text-sm text-gray-700">
                        <p className="font-medium text-gray-900">Saved external state</p>
                        <p className="mt-1">Health: {agent.a2a_config.health_status}</p>
                        <p>Sync: {agent.a2a_config.sync_status}</p>
                        <p>Imported skill: {agent.a2a_config.remote_skill_name}</p>
                      </div>
                    )}
                  </div>
                )}

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
          )}

          {/* TAB 2: PROMPTS */}
          {activeTab === 'prompts' && (
            <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-8">
              <div className="flex items-center mb-6">
                <div className="w-10 h-10 bg-purple-100 rounded-xl flex items-center justify-center mr-4">
                  <MessageSquare className="w-5 h-5 text-purple-600" />
                </div>
                <h3 className="text-xl font-semibold text-gray-900">Prompts & Instructions</h3>
              </div>
              
              <div className="space-y-6">
                {isA2AAgent ? (
                  <div className="rounded-2xl border border-blue-200 bg-blue-50 p-6 text-sm text-blue-900">
                    Imported A2A agents execute through the selected remote skill. Local system prompts and prompt templates are disabled in Phase 1 so the imported agent stays faithful to the upstream capability. The Tool Agent option remains available so the imported agent can still be exposed through MCP servers.
                  </div>
                ) : (
                <>
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
                  <p className="text-xs text-gray-500 mt-2 flex items-center gap-1"><Lightbulb className="w-3 h-3" /> The template must include {'{question}'} to work properly</p>
                </div>

                {/* Memory Management - Conditional */}
                {formData.has_memory && (
                  <div className="border-t border-gray-200 pt-6">
                    <div className="flex items-center mb-6">
                      <div className="w-10 h-10 bg-indigo-100 rounded-xl flex items-center justify-center mr-4">
                        <Brain className="w-5 h-5 text-indigo-600" />
                      </div>
                      <div className="flex-1">
                        <h3 className="text-lg font-semibold text-gray-900">Memory Management</h3>
                        <p className="text-sm text-gray-600 mt-1">Configura la estrategia de gestión de memoria del agente</p>
                      </div>
                    </div>

                    <div className="mb-6 p-4 bg-indigo-50 rounded-xl">
                      <div className="flex items-start">
                        <Info className="w-5 h-5 text-indigo-500 mr-3 shrink-0" />
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
                          onChange={(e) => handleInputChange('memory_max_messages', Number.parseInt(e.target.value))}
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
                          onChange={(e) => handleInputChange('memory_max_tokens', Number.parseInt(e.target.value))}
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
                          onChange={(e) => handleInputChange('memory_summarize_threshold', Number.parseInt(e.target.value))}
                          className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 transition-all duration-200"
                        />
                        <p className="text-xs text-gray-500 mt-2">
                          Número de mensajes antiguos a partir del cual se considera resumir (futura implementación, recomendado: 10)
                        </p>
                      </div>
                    </div>

                    <div className="mt-6 p-4 bg-gray-50 rounded-xl">
                      <h4 className="text-sm font-semibold text-gray-900 mb-2 flex items-center gap-1"><BarChart2 className="w-4 h-4" /> Configuración Actual:</h4>
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
                </>
                )}
              </div>
            </div>
          )}

          {/* TAB 3: CONFIGURATION */}
          {activeTab === 'configuration' && (
            <div className="space-y-6">
              {isA2AAgent && (
                <div className="bg-white rounded-2xl shadow-sm border border-blue-200 p-8 text-sm text-blue-900">
                  External A2A agents do not use a local AI service, RAG silo, output parser, or code interpreter in Phase 1. The imported remote skill is the execution backend.
                </div>
              )}
              {/* Configuration for regular local agents */}
              {formData.type !== 'ocr_agent' && !isA2AAgent && (
                <>
                  <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-8">
                    <div className="flex items-center mb-6">
                      <div className="w-10 h-10 bg-orange-100 rounded-xl flex items-center justify-center mr-4">
                        <Settings className="w-5 h-5 text-orange-600" />
                      </div>
                      <h3 className="text-xl font-semibold text-gray-900">Configuration</h3>
                    </div>
                    
                    {/* No AI Services Warning */}
                    {agent?.ai_services.length === 0 && renderNoAIServicesWarning(false)}

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                      <div>
                        <label htmlFor="ai_service" className="block text-sm font-medium text-gray-700 mb-2">
                          AI Service *
                        </label>
                        <select
                          id="ai_service"
                          value={formData.service_id || ''}
                          onChange={(e) => handleInputChange('service_id', e.target.value ? Number.parseInt(e.target.value) : undefined)}
                          className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all duration-200"
                          required
                        >
                          <option value="">Select AI Service</option>
                          {agent?.ai_services.map((service) => (
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
                          onChange={(e) => handleInputChange('silo_id', e.target.value ? Number.parseInt(e.target.value) : undefined)}
                          className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all duration-200"
                        >
                          <option value="">Select Knowledge Base</option>
                          {agent?.silos.map((silo) => (
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
                            onChange={(e) => handleInputChange('temperature', Number.parseFloat(e.target.value))}
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

                      <div>
                        <OutputParserField
                          showOutputParser={showOutputParser}
                          setShowOutputParser={setShowOutputParser}
                          formData={formData}
                          handleInputChange={handleInputChange}
                          agent={agent}
                        />
                      </div>
                    </div>
                  </div>

                </>
              )}

              {/* Agent Capabilities Card */}
              {formData.type !== 'ocr_agent' && (
                <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-8">
                  <div className="flex items-center mb-6">
                    <div className="w-10 h-10 bg-green-100 rounded-xl flex items-center justify-center mr-4">
                      <Zap className="w-5 h-5 text-green-600" />
                    </div>
                    <h3 className="text-xl font-semibold text-gray-900">Capabilities</h3>
                  </div>

                  {/* MCP Warning Dialog */}
                  {showMcpWarning && mcpUsage && mcpUsage.mcp_servers.length > 0 && (
                    <div className="mb-6 bg-amber-50 border border-amber-200 rounded-xl p-4">
                      <div className="flex items-start">
                        <span className="text-amber-500 text-xl mr-3">!</span>
                        <div className="flex-1">
                          <h4 className="text-sm font-semibold text-amber-900 mb-2">
                            This agent is used in {mcpUsage.mcp_servers.length} MCP server{mcpUsage.mcp_servers.length === 1 ? '' : 's'}
                          </h4>
                          <p className="text-sm text-amber-800 mb-2">
                            Unmarking this agent as a tool will make it unavailable in the following MCP servers:
                          </p>
                          <ul className="text-sm text-amber-700 list-disc list-inside mb-3">
                            {mcpUsage.mcp_servers.map(s => (
                              <li key={s.server_id}>{s.server_name}</li>
                            ))}
                          </ul>
                          <div className="flex space-x-3">
                            <button
                              type="button"
                              onClick={() => {
                                handleInputChange('is_tool', false);
                                setShowMcpWarning(false);
                              }}
                              className="px-4 py-2 bg-amber-600 hover:bg-amber-700 text-white text-sm font-medium rounded-lg transition-colors"
                            >
                              Unmark as Tool Anyway
                            </button>
                            <button
                              type="button"
                              onClick={() => setShowMcpWarning(false)}
                              className="px-4 py-2 bg-gray-200 hover:bg-gray-300 text-gray-800 text-sm font-medium rounded-lg transition-colors"
                            >
                              Cancel
                            </button>
                          </div>
                        </div>
                      </div>
                    </div>
                  )}

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <div className="flex items-center p-4 bg-gray-50 rounded-xl">
                      <input
                        id="is_tool"
                        type="checkbox"
                        checked={formData.is_tool}
                        onChange={(e) => {
                          if (!e.target.checked && mcpUsage && mcpUsage.mcp_servers.length > 0) {
                            setShowMcpWarning(true);
                          } else {
                            handleInputChange('is_tool', e.target.checked);
                          }
                        }}
                        className="w-5 h-5 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                      />
                      <div className="ml-3">
                        <label htmlFor="is_tool" className="text-sm font-medium text-gray-900">Tool Agent</label>
                        <p className="text-xs text-gray-500">
                          {isA2AAgent ? 'Expose this imported A2A agent through MCP servers and other agents.' : 'Can be used by other agents'}
                        </p>
                        {mcpUsage && mcpUsage.mcp_servers.length > 0 && formData.is_tool && (
                          <p className="text-xs text-purple-600 mt-1">
                            Used in {mcpUsage.mcp_servers.length} MCP server{mcpUsage.mcp_servers.length === 1 ? '' : 's'}
                          </p>
                        )}
                      </div>
                    </div>

                    {!isA2AAgent && (
                      <>
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

                        <div className="flex items-center p-4 bg-gray-50 rounded-xl">
                          <input
                            id="enable_code_interpreter"
                            type="checkbox"
                            checked={formData.enable_code_interpreter}
                            onChange={(e) => handleInputChange('enable_code_interpreter', e.target.checked)}
                            className="w-5 h-5 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                          />
                          <div className="ml-3">
                            <label htmlFor="enable_code_interpreter" className="text-sm font-medium text-gray-900">Code Interpreter</label>
                            <p className="text-xs text-gray-500">Allows the agent to execute Python code (pandas, openpyxl, numpy)</p>
                          </div>
                        </div>
                      </>
                    )}
                  </div>

                  {!isA2AAgent && (
                    <div className="mt-6 pt-6 border-t border-gray-100">
                      <div className="mb-3">
                        <h4 className="text-sm font-semibold text-gray-800">Provider-side Tools</h4>
                        <p className="text-xs text-gray-500 mt-0.5">
                          These tools run on the AI provider's infrastructure — no extra backend setup needed.
                          Only tools supported by the agent's selected provider will be active.
                        </p>
                      </div>
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                        {[
                          {
                            id: 'web_search',
                            icon: <Search className="w-4 h-4" />,
                            label: 'Web Search',
                            description: 'Real-time internet search',
                            providers: ['OpenAI', 'Anthropic', 'Google', 'Azure'],
                          },
                          {
                            id: 'image_generation',
                            icon: <Image className="w-4 h-4" />,
                            label: 'Image Generation',
                            description: 'Generate images with DALL-E',
                            providers: ['OpenAI', 'Azure'],
                          },
                          {
                            id: 'code_interpreter',
                            icon: <Terminal className="w-4 h-4" />,
                            label: 'Code Interpreter',
                            description: 'Provider-sandboxed code execution',
                            providers: ['OpenAI', 'Anthropic', 'Azure'],
                          },
                          {
                            id: 'file_search',
                            icon: <FolderSearch className="w-4 h-4" />,
                            label: 'File Search',
                            description: 'Vector search over uploaded files',
                            providers: ['OpenAI', 'Azure'],
                          },
                        ].map((tool) => {
                          const active = formData.server_tools.includes(tool.id);
                          const toggle = () => handleInputChange(
                            'server_tools',
                            active
                              ? formData.server_tools.filter(t => t === tool.id)
                              : [...formData.server_tools, tool.id]
                          );
                          return (
                            <button
                              key={tool.id}
                              type="button"
                              onClick={toggle}
                              className={`text-left p-3 rounded-xl border-2 transition-colors ${
                                active
                                  ? 'border-blue-500 bg-blue-50'
                                  : 'border-gray-200 bg-gray-50 hover:border-gray-300'
                              }`}
                            >
                              <div className="flex items-center gap-2 mb-1">
                                <span className="text-base">{tool.icon}</span>
                                <span className={`text-sm font-medium ${active ? 'text-blue-800' : 'text-gray-800'}`}>
                                  {tool.label}
                                </span>
                                {active && (
                                  <span className="ml-auto text-xs font-medium text-blue-600 bg-blue-100 px-1.5 py-0.5 rounded-full">ON</span>
                                )}
                              </div>
                              <p className="text-xs text-gray-500 mb-2">{tool.description}</p>
                              <div className="flex flex-wrap gap-1">
                                {tool.providers.map(p => (
                                  <span key={p} className="text-xs px-1.5 py-0.5 rounded bg-gray-200 text-gray-600">{p}</span>
                                ))}
                              </div>
                            </button>
                          );
                        })}
                      </div>
                      <p className="text-xs text-amber-600 mt-3 flex items-start gap-1">
                        <AlertTriangle className="w-3 h-3 shrink-0 mt-0.5" /> Some tools require specific models — e.g. Image Generation needs gpt-image-1 (OpenAI Responses API).
                        Unsupported tools for the selected provider are silently ignored.
                      </p>
                    </div>
                  )}
                </div>
              )}

              {/* Configuration for OCR agents */}
              {formData.type === 'ocr_agent' && (
                <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-8">
                  <div className="flex items-center mb-6">
                    <div className="w-10 h-10 bg-blue-100 rounded-xl flex items-center justify-center mr-4">
                      <FileText className="w-5 h-5 text-blue-600" />
                    </div>
                    <h3 className="text-xl font-semibold text-gray-900">OCR Configuration</h3>
                  </div>
                  
                  {/* No AI Services Warning */}
                  {agent?.ai_services.length === 0 && renderNoAIServicesWarning(true)}

                  <div className="space-y-6">
                    <div>
                      <label htmlFor="vision_service" className="block text-sm font-medium text-gray-700 mb-2">
                        Modelo de Visión
                      </label>
                      <select
                        id="vision_service"
                        value={formData.vision_service_id || ''}
                        onChange={(e) => handleInputChange('vision_service_id', e.target.value ? Number.parseInt(e.target.value) : undefined)}
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
                        onChange={(e) => handleInputChange('service_id', e.target.value ? Number.parseInt(e.target.value) : undefined)}
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
            </div>
          )}

          {/* TAB 4: ADVANCED */}
          {activeTab === 'advanced' && (
            <div className="space-y-6">
              {isA2AAgent && (
                <div className="bg-white rounded-2xl shadow-sm border border-blue-200 p-8 text-sm text-blue-900">
                  Most native MattinAI execution-shaping capabilities are intentionally disabled for imported A2A agents in Phase 1. This keeps the imported agent a pure wrapper around the selected external skill, while still allowing it to be marked as a Tool Agent and exposed through MCP servers.
                </div>
              )}
              {/* Tools Card - Only for regular agents */}
              {agent && agent.tools.length > 0 && formData.type !== 'ocr_agent' && !isA2AAgent && (
                <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-8">
                  <div className="flex items-center mb-6">
                    <div className="w-10 h-10 bg-yellow-100 rounded-xl flex items-center justify-center mr-4">
                      <Wrench className="w-5 h-5 text-yellow-600" />
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
                        <span className="font-medium">{formData.tool_ids.length}</span> tool{formData.tool_ids.length === 1 ? '' : 's'} selected
                      </p>
                    </div>
                  )}
                </div>
              )}

              {/* MCP Configs Card - Only for regular agents */}
              {agent?.mcp_configs && formData.type !== 'ocr_agent' && !isA2AAgent && (
                <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-8">
                  <div className="flex items-center mb-6">
                    <div className="w-10 h-10 bg-purple-100 rounded-xl flex items-center justify-center mr-4">
                      <Plug className="w-5 h-5 text-purple-600" />
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
                          <Info className="w-5 h-5 text-purple-500 mr-3 shrink-0" />
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
                            <span className="font-medium">{formData.mcp_config_ids.length}</span> MCP server{formData.mcp_config_ids.length === 1 ? '' : 's'} selected
                          </p>
                        </div>
                      )}
                    </>
                  ) : (
                    <div className="text-center py-8">
                      <div className="w-16 h-16 bg-gray-100 rounded-full flex items-center justify-center mx-auto mb-4">
                        <Plug className="w-8 h-8 text-gray-400" />
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
                        <Settings className="w-4 h-4 mr-2" />
                        {' '}Configure MCP Servers
                      </button>
                    </div>
                  )}
                </div>
              )}

              {/* Skills Card - Only for regular agents */}
              {agent?.skills && formData.type !== 'ocr_agent' && !isA2AAgent && (
                <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-8">
                  <div className="flex items-center justify-between mb-6">
                    <div>
                      <h3 className="text-xl font-semibold text-gray-900 flex items-center">
                        <Target className="w-5 h-5 mr-3" />
                        {' '}Skills
                      </h3>
                      <p className="text-gray-600 mt-1">Assign specialized behaviors that the agent can activate on-demand</p>
                    </div>
                  </div>

                  {agent.skills.length > 0 ? (
                    <>
                      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                        {agent.skills.map((skill) => (
                          <button
                            key={skill.skill_id}
                            type="button"
                            className={`p-4 rounded-xl border-2 cursor-pointer transition-all duration-200 text-left w-full ${
                              formData.skill_ids.includes(skill.skill_id)
                                ? 'border-purple-500 bg-purple-50'
                                : 'border-gray-200 bg-gray-50 hover:border-gray-300'
                            }`}
                            onClick={() => handleSkillToggle(skill.skill_id)}
                          >
                            <div className="flex items-center justify-between">
                              <div className="flex items-center">
                                <input
                                  type="checkbox"
                                  checked={formData.skill_ids.includes(skill.skill_id)}
                                  onChange={() => handleSkillToggle(skill.skill_id)}
                                  className="w-4 h-4 rounded border-gray-300 text-purple-600 focus:ring-purple-500"
                                />
                                <span className="ml-3 text-sm font-medium text-gray-900">{skill.name}</span>
                              </div>
                              <div className={`w-2 h-2 rounded-full ${
                                formData.skill_ids.includes(skill.skill_id) ? 'bg-purple-500' : 'bg-gray-300'
                              }`} />
                            </div>
                            {skill.description && (
                              <p className="mt-2 ml-7 text-xs text-gray-500 truncate">{skill.description}</p>
                            )}
                          </button>
                        ))}
                      </div>

                      {formData.skill_ids.length > 0 && (
                        <div className="mt-4 p-4 bg-purple-50 rounded-xl">
                          <p className="text-sm text-purple-800">
                            <span className="font-medium">{formData.skill_ids.length}</span> skill{formData.skill_ids.length === 1 ? '' : 's'} selected.
                            The agent will have a <code className="bg-purple-100 px-1 rounded">load_skill</code> tool to activate these skills.
                          </p>
                        </div>
                      )}
                    </>
                  ) : (
                    <div className="text-center py-8">
                      <div className="w-16 h-16 bg-gray-100 rounded-full flex items-center justify-center mx-auto mb-4">
                        <Target className="w-8 h-8 text-gray-400" />
                      </div>
                      <h4 className="text-lg font-medium text-gray-900 mb-2">No Skills Available</h4>
                      <p className="text-gray-500 mb-4">
                        You haven't created any skills yet. Create skills in the settings to enable specialized agent behaviors.
                      </p>
                      <button
                        type="button"
                        onClick={() => navigate(`/apps/${appId}/skills`)}
                        className="inline-flex items-center px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white text-sm font-medium rounded-lg transition-colors"
                      >
                        <Target className="w-4 h-4 mr-2" />
                        {' '}Manage Skills
                      </button>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* TAB 5: MARKETPLACE */}
          {activeTab === 'marketplace' && (
            <div className="bg-white rounded-2xl shadow-sm border border-blue-200 p-8 mb-8">
              <div className="flex items-center mb-6">
                <div className="w-10 h-10 bg-blue-100 rounded-xl flex items-center justify-center mr-4">
                  <Store className="w-5 h-5 text-blue-600" aria-hidden="true" />
                </div>
                <h3 className="text-xl font-semibold text-gray-900">Marketplace Publishing</h3>
              </div>

              {/* New agent: prompt user to save first */}
              {isNewAgent ? (
                <div className="flex items-start gap-3 p-4 bg-blue-50 border border-blue-200 rounded-xl text-sm text-blue-800">
                  <Info className="w-4 h-4 shrink-0" aria-hidden="true" />
                  <span>Save the agent first to configure marketplace publishing.</span>
                </div>
              ) : (
              <>
              {/* Visibility Control */}
              <div className="mb-6">
                <label htmlFor="marketplace-visibility" className="block text-sm font-medium text-gray-700 mb-2">Marketplace Visibility</label>
                <div className="flex items-center gap-4">
                  <select
                    id="marketplace-visibility"
                    value={marketplaceVisibility}
                    onChange={(e) => handleVisibilityChange(e.target.value as MarketplaceVisibility)}
                    disabled={formData.is_tool}
                    className="px-4 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all duration-200"
                  >
                    <option value="unpublished">Unpublished (not listed)</option>
                    <option value="private">Private (visible to app members only)</option>
                    <option value="public">Public (visible to all users)</option>
                  </select>
                  {formData.is_tool && (
                    <span className="text-xs text-gray-500 ml-2">Tool agents cannot be published to the marketplace</span>
                  )}
                </div>
              </div>

              {/* Profile Metadata (expandable) */}
              {showMarketplace && (
                <div className="space-y-6">
                  <div>
                    <label htmlFor="marketplace-display-name" className="block text-sm font-medium text-gray-700 mb-2">Display Name</label>
                    <input
                      id="marketplace-display-name"
                      type="text"
                      value={marketplaceProfile.display_name ?? ''}
                      onChange={(e) => handleMarketplaceProfileChange('display_name', e.target.value)}
                      maxLength={255}
                      placeholder="Defaults to agent name if empty"
                      className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all duration-200"
                    />
                  </div>
                  <div>
                    <label htmlFor="marketplace-short-description" className="block text-sm font-medium text-gray-700 mb-2">Short Description</label>
                    <textarea
                      id="marketplace-short-description"
                      value={marketplaceProfile.short_description ?? ''}
                      onChange={(e) => handleMarketplaceProfileChange('short_description', e.target.value)}
                      maxLength={200}
                      rows={2}
                      className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all duration-200"
                    />
                    <div className="text-xs text-gray-500 mt-1">
                      {marketplaceProfile.short_description?.length ?? 0}/200 characters
                    </div>
                  </div>
                  <div>
                    <label htmlFor="marketplace-long-description" className="block text-sm font-medium text-gray-700 mb-2">Long Description</label>
                    <textarea
                      id="marketplace-long-description"
                      value={marketplaceProfile.long_description ?? ''}
                      onChange={(e) => handleMarketplaceProfileChange('long_description', e.target.value)}
                      rows={4}
                      placeholder="Supports Markdown"
                      className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all duration-200"
                    />
                  </div>
                  <div>
                    <label htmlFor="marketplace-category" className="block text-sm font-medium text-gray-700 mb-2">Category</label>
                    <select
                      id="marketplace-category"
                      value={marketplaceProfile.category ?? ''}
                      onChange={(e) => handleMarketplaceProfileChange('category', e.target.value)}
                      className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all duration-200"
                    >
                      <option value="">-- Select a category --</option>
                      {MARKETPLACE_CATEGORIES.map((cat) => (
                        <option key={cat} value={cat}>{cat}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label htmlFor="marketplace-tags" className="block text-sm font-medium text-gray-700 mb-2">Tags</label>
                    <TagInput
                      id="marketplace-tags"
                      tags={marketplaceProfile.tags ?? []}
                      onChange={(tags) => handleMarketplaceProfileChange('tags', tags)}
                      maxTags={5}
                      placeholder="Add up to 5 tags"
                    />
                  </div>
                  <div>
                    <label htmlFor="marketplace-icon-url" className="block text-sm font-medium text-gray-700 mb-2">Icon URL</label>
                    <input
                      id="marketplace-icon-url"
                      type="text"
                      value={marketplaceProfile.icon_url ?? ''}
                      onChange={(e) => handleMarketplaceProfileChange('icon_url', e.target.value)}
                      placeholder="https://..."
                      className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all duration-200"
                    />
                    {marketplaceProfile.icon_url && (
                      <img
                        src={marketplaceProfile.icon_url}
                        alt="Icon preview"
                        className="mt-2 w-10 h-10 rounded"
                        onError={(e) => (e.currentTarget.style.display = 'none')}
                      />
                    )}
                  </div>
                  <div>
                    <label htmlFor="marketplace-cover-image-url" className="block text-sm font-medium text-gray-700 mb-2">Cover Image URL</label>
                    <input
                      id="marketplace-cover-image-url"
                      type="text"
                      value={marketplaceProfile.cover_image_url ?? ''}
                      onChange={(e) => handleMarketplaceProfileChange('cover_image_url', e.target.value)}
                      placeholder="https://..."
                      className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all duration-200"
                    />
                    {marketplaceProfile.cover_image_url && (
                      <img
                        src={marketplaceProfile.cover_image_url}
                        alt="Cover preview"
                        className="mt-2 w-32 h-16 rounded object-cover"
                        onError={(e) => (e.currentTarget.style.display = 'none')}
                      />
                    )}
                  </div>
                  <div className="flex items-center gap-4 mt-4">
                    <button
                      type="button"
                      onClick={handleSaveMarketplaceProfile}
                      className="px-6 py-2 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors"
                      disabled={savingMarketplace}
                    >
                      {savingMarketplace ? 'Saving...' : 'Save Marketplace Profile'}
                    </button>
                    {marketplaceSuccess && (
                      <span className="text-sm text-green-600">{marketplaceSuccess}</span>
                    )}
                  </div>
                </div>
              )}
              </>
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
