import { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { AlertTriangle, Settings, FileText, Lightbulb, Zap, Search, Image, Terminal, FolderSearch,  Target, Plus, Tv, MessageSquare, Plug, Wrench, Store } from 'lucide-react';
import { apiService, ApiError, type ScheduledTask } from '../services/api';
import { useApiMutation } from '../hooks/useApiMutation';
import { MESSAGES, errorMessage } from '../constants/messages';
import { DEFAULT_AGENT_TEMPERATURE, DEFAULT_PROMPT_TEMPLATE } from '../constants/agentConstants';
import Alert from '../components/ui/Alert';
import AgentMiddlewaresCard, { type AgentMiddlewareOption } from '../components/forms/AgentMiddlewaresCard';
import { Badge,ProviderBadge } from '../components/ui/Badge';
import { TagInput } from '../components/ui/TagInput';
import { Tabs } from '../components/ui/Tabs';
import { ServiceOptionStatus, serviceStatusId } from '../components/ui/ServiceOptionStatus';
import { selectableServiceOptions, serviceOptionLabel, type ServiceOptionLike } from '../utils/serviceLifecycle';
import type { TabItem } from '../components/ui/Tabs';
import { FormCheckbox, FormField, FormSelect, FormTextArea } from '../components/ui/FormField';
import ButtonCard from '../components/ui/ButtonCard';
import RagConfigSection, { SCORE_THRESHOLD_REQUIRED_MSG } from '../components/forms/RagConfigSection';
import type { RagConfigValue, RagFixedFilter, RagSearchType } from '../components/forms/RagConfigSection';
import type { SearchFilterMetadataField } from '../components/playground/SearchFilters';
import type { AgentMCPUsage } from '../core/types';
import type { MarketplaceVisibility, MarketplaceProfileUpdate } from '../types/marketplace';
import { MARKETPLACE_CATEGORIES } from '../types/marketplace';
import { AgentMetricsTab } from '../components/metrics/AgentMetricsTab';
import { AgentA2ASettings } from '../components/forms/AgentA2ASettings';
import type { A2ACardVisibility, AgentA2AFieldErrors, AgentA2AValue } from '../components/forms/AgentA2ASettings';
import { useAppRole } from '../hooks/useAppRole';
import { AppRole } from '../types/roles';
import { randomId } from '../utils/randomId';
import Title from '../components/ui/Title';
import ButtonApp from '../components/ui/ButtonApp';
import { FormActions } from '../components/ui/FormActions';
import BackgroundImage from '../components/ui/BackgroundImage';
import { CardApp } from '../components/ui/CardApp';
import { LoadingState } from '../components/ui/LoadingState';
import type { ServiceLifecycleWarning } from '../types/services';
import ServiceLifecycleAlert from '../components/services/ServiceLifecycleAlert';

// Define the Agent types
interface Agent {
  agent_id: number;
  name: string;
  description?: string;
  system_prompt: string;
  prompt_template: string;
  type: string;
  is_tool: boolean;
  has_memory: boolean;
  enable_code_interpreter: boolean;
  lifecycle_warnings?: ServiceLifecycleWarning[];
  skill_router_enabled?: boolean;
  service_id?: number;
  sandbox_service_id?: number;
  silo_id?: number;
  output_parser_id?: number;
  temperature: number;
  tool_ids?: number[];
  mcp_config_ids?: number[];
  skill_ids?: number[];
  created_at: string;
  request_count: number;
  marketplace_visibility?: MarketplaceVisibility;
  // A2A (Agent2Agent protocol) exposure
  a2a_enabled?: boolean;
  a2a_card_visibility?: A2ACardVisibility;
  a2a_name_override?: string | null;
  a2a_description_override?: string | null;
  a2a_skill_tags?: string[];
  a2a_examples?: string[];
  a2a_card_url?: string | null;
  a2a_rpc_url?: string | null;
  // OCR-specific fields
  vision_service_id?: number;
  vision_system_prompt?: string;
  text_system_prompt?: string;
  // RAG retrieval config
  rag_k?: number;
  rag_search_type?: RagSearchType;
  rag_score_threshold?: number | null;
  rag_max_retrieval_calls?: number | null;
  rag_fixed_filters?: RagFixedFilter[];
  // Media processing configuration (playground media upload)
  transcription_service_id?: number | null;
  video_ai_service_id?: number | null;
  media_embedding_service_id?: number | null;
  media_forced_language?: string | null;
  media_chunk_min_duration?: number | null;
  media_chunk_max_duration?: number | null;
  media_chunk_overlap?: number | null;
  ai_services: Array<ServiceOptionLike & { supports_video?: boolean }>;
  sandbox_services: ServiceOptionLike[];
  silos: Array<{ silo_id: number; name: string }>;
  output_parsers: Array<{ parser_id: number; name: string }>;
  tools: Array<{ agent_id: number; name: string }>;
  mcp_configs: Array<{ config_id: number; name: string }>;
  skills: Array<{ skill_id: number; name: string; description?: string; is_enabled?: boolean; is_system?: boolean }>;
  middlewares?: AgentMiddlewareOption[];
}

interface AgentFormData {
  name: string;
  description: string;
  system_prompt: string;
  prompt_template: string;
  type: string;
  is_tool: boolean;
  has_memory: boolean;
  enable_code_interpreter: boolean;
  skill_router_enabled: boolean;
  server_tools: string[];
  service_id?: number;
  sandbox_service_id?: number;
  silo_id?: number;
  output_parser_id?: number;
  temperature: number;
  tool_ids: number[];
  mcp_config_ids: number[];
  skill_ids: number[];
  middleware_ids: number[];
  // OCR-specific fields
  vision_service_id?: number;
  vision_system_prompt?: string;
  text_system_prompt?: string;
  // RAG retrieval config
  rag_k: number;
  rag_search_type: RagSearchType;
  rag_score_threshold: number | null;
  rag_max_retrieval_calls: number | null;
  rag_fixed_filters: RagFixedFilter[];
  // Media processing configuration (playground media upload)
  transcription_service_id?: number;
  video_ai_service_id?: number;
  media_embedding_service_id?: number;
  media_forced_language?: string;
  media_chunk_min_duration: number;
  media_chunk_max_duration: number;
  media_chunk_overlap: number;
  // A2A (Agent2Agent protocol) exposure
  a2a_enabled: boolean;
  a2a_card_visibility: A2ACardVisibility;
  a2a_name_override: string | null;
  a2a_description_override: string | null;
  a2a_skill_tags: string[];
  a2a_examples: string[];
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
    <FormCheckbox
      id="output_parser_toggle"
      label="Data Structure"
      checked={showOutputParser}
      onChange={(e) => {
        setShowOutputParser(e.target.checked);
        if (!e.target.checked) {
          handleInputChange('output_parser_id', undefined);
        }
      }}
      className="mb-2"
    />

    {showOutputParser && (
      <FormSelect
        label="Data Structure"
        id="output_parser"
        value={formData.output_parser_id || ''}
        onChange={(e) =>
          handleInputChange(
            'output_parser_id',
            e.target.value ? Number.parseInt(e.target.value) : undefined
          )
        }
        options={[
          { value: '', label: '-- Select a Data Structure --' },
          ...(agent?.output_parsers.map((parser) => ({
            value: parser.parser_id,
            label: parser.name,
          })) ?? []),
        ]}
      />
    )}
  </div>
);

/**
 * Pull per-field messages for a2a_* keys out of a FastAPI 422 `detail` array
 * (each item's `loc` looks like `["body", "a2a_name_override"]`). Returns null
 * when the error isn't a 422 with any a2a_* location, so callers can fall back
 * to the generic top-level banner.
 */
function extractA2AFieldErrors(err: unknown): AgentA2AFieldErrors | null {
  if (!(err instanceof ApiError) || err.status !== 422 || !Array.isArray(err.detail)) {
    return null;
  }
  const errors: AgentA2AFieldErrors = {};
  for (const item of err.detail) {
    if (!item || typeof item !== 'object') continue;
    const loc = (item as { loc?: unknown }).loc;
    const msg = (item as { msg?: unknown }).msg;
    if (!Array.isArray(loc) || typeof msg !== 'string') continue;
    const field = loc.find((segment) => typeof segment === 'string' && segment.startsWith('a2a_'));
    if (typeof field !== 'string') continue;
    const key = field as keyof AgentA2AFieldErrors;
    if (!errors[key]) errors[key] = msg;
  }
  return Object.keys(errors).length > 0 ? errors : null;
}

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

function ScheduledTaskReference({ appId, agentId }: { appId: number; agentId: number }) {
  const [tasks, setTasks] = useState<ScheduledTask[]>([]);
  useEffect(() => { void apiService.getScheduledTasks(appId, agentId).then(setTasks).catch(() => undefined); }, [appId, agentId]);
  return <section className="mb-6 rounded-md border border-line bg-surface dark:border-line-dark dark:bg-surface-dark p-6 "><div className="flex flex-wrap items-center justify-between gap-3"><div><h3 className="text-lg font-semibold text-fg dark:text-fg-dark">Scheduled tasks using this agent</h3><p className="text-sm text-fg-secondary dark:text-fg-secondary-dark">Scheduling is managed independently from the agent.</p></div>
    <ButtonApp
      type="button"
      onClick={() => globalThis.location.assign(`/apps/${appId}/scheduled-tasks/new`)}
      variant="primary"
      label="Create scheduled task"
    ></ButtonApp>
    
    </div>{tasks.length > 0 && <div className="mt-4 space-y-2">{tasks.map((task) => <a key={task.id} href={`/apps/${appId}/scheduled-tasks/${task.id}`} className="flex items-center justify-between rounded-md bg-surface dark:bg-surface-dark border border-line dark:border-btCard-border-dark px-3 py-2 text-sm"><span>{task.name}</span><span className="text-fg-tertiary dark:text-fg-tertiary-dark">{task.status === 'active' ? 'Active' : 'Paused'}</span></a>)}</div>}</section>;
}

function AgentFormPage() {
  const { appId, agentId } = useParams();
  const navigate = useNavigate();
  const mutate = useApiMutation();
  const { hasMinRole } = useAppRole(appId);
  const canEditA2A = hasMinRole(AppRole.EDITOR);
  const [agent, setAgent] = useState<Agent | null>(null);
  const [a2aCardUrl, setA2aCardUrl] = useState<string | null>(null);
  const [a2aRpcUrl, setA2aRpcUrl] = useState<string | null>(null);
  const [a2aFieldErrors, setA2aFieldErrors] = useState<AgentA2AFieldErrors>({});
  const [loading, setLoading] = useState(true);
  const [mcpUsage, setMcpUsage] = useState<AgentMCPUsage | null>(null);
  const [showMcpWarning, setShowMcpWarning] = useState(false);
  const [activeTab, setActiveTab] = useState<string>('basic');

  const starterRefs = useRef<(HTMLInputElement | null)[]>([]);

  // Helper function to render the "No AI Services" warning banner
  const renderNoAIServicesWarning = (isOcrAgent: boolean) => {
    const message = isOcrAgent
      ? 'You need to configure at least one AI service before creating an OCR agent. AI services define which models your agent will use for vision and text processing.'
      : 'You need to configure at least one AI service before creating an agent. AI services define which language model your agent will use.';

    return (
      <Alert
        type="warning"
        title="No AI Services Configured"
        className="mb-6"
        message={(
          <>
            {message}
            <span className="mt-3 block">
              <ButtonApp
                label="Configure AI Services"
                variant="secondary"
                size="small"
                icon={<Settings className="w-4 h-4" />}
                onClick={() => navigate(`/apps/${appId}/settings/ai-services`)}
              />
            </span>
          </>
        )}
      />
    );
  };
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [formData, setFormData] = useState<AgentFormData>({
    name: '',
    description: '',
    system_prompt: '',
    prompt_template: DEFAULT_PROMPT_TEMPLATE,
    type: 'agent',
    is_tool: false,
    has_memory: false,
    enable_code_interpreter: false,
    skill_router_enabled: false,
    server_tools: [],
    temperature: DEFAULT_AGENT_TEMPERATURE,
    tool_ids: [],
    mcp_config_ids: [],
    skill_ids: [],
    middleware_ids: [],
    rag_k: 10,
    rag_search_type: 'similarity',
    rag_score_threshold: null,
    rag_max_retrieval_calls: 4,
    rag_fixed_filters: [],
    media_embedding_service_id: undefined,
    media_chunk_min_duration: 30,
    media_chunk_max_duration: 120,
    media_chunk_overlap: 5,
    a2a_enabled: false,
    a2a_card_visibility: 'public',
    a2a_name_override: null,
    a2a_description_override: null,
    a2a_skill_tags: [],
    a2a_examples: [],
  });
  const [showOutputParser, setShowOutputParser] = useState(false);
  const [siloMetadataFields, setSiloMetadataFields] = useState<SearchFilterMetadataField[]>([]);
  const [loadingSiloMetadata, setLoadingSiloMetadata] = useState(false);
  const [embeddingServices, setEmbeddingServices] = useState<ServiceOptionLike[]>([]);

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
    conversation_starters: [],
  });

  // Load agent data when component mounts
  useEffect(() => {
    if (appId && agentId) {
      void loadAgentData();
    } else {
      setLoading(false);
    }
  }, [appId, agentId]);

  // Load the app's embedding services to populate the media embedding selector.
  useEffect(() => {
    if (!appId) return;
    let cancelled = false;
    apiService
      .getEmbeddingServices(Number.parseInt(appId))
      .then((services) => {
        if (cancelled) return;
        const list = Array.isArray(services) ? services : [];
        setEmbeddingServices(
          list.map((s: ServiceOptionLike) => ({
            service_id: s.service_id,
            name: s.name,
            lifecycle_status: s.lifecycle_status,
            end_of_service_at: s.end_of_service_at,
            deprecation_notice: s.deprecation_notice,
          }))
        );
      })
      .catch((err) => {
        console.error('Error loading embedding services:', err);
        setEmbeddingServices([]);
      });
    return () => {
      cancelled = true;
    };
  }, [appId]);

  // Load the selected silo's metadata fields to power the fixed-filter editor.
  useEffect(() => {
    const siloId = formData.silo_id;
    if (!appId || !siloId) {
      setSiloMetadataFields([]);
      return;
    }
    let cancelled = false;
    setLoadingSiloMetadata(true);
    apiService
      .getSilo(Number.parseInt(appId), siloId)
      .then((silo) => {
        if (!cancelled) setSiloMetadataFields(silo?.metadata_fields ?? []);
      })
      .catch(() => {
        if (!cancelled) setSiloMetadataFields([]);
      })
      .finally(() => {
        if (!cancelled) setLoadingSiloMetadata(false);
      });
    return () => {
      cancelled = true;
    };
  }, [appId, formData.silo_id]);

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
        prompt_template: response.prompt_template || DEFAULT_PROMPT_TEMPLATE,
        type: response.type || 'agent',
        is_tool: response.is_tool || false,
        has_memory: response.has_memory || false,
        enable_code_interpreter: response.enable_code_interpreter || false,
        skill_router_enabled: response.skill_router_enabled || false,
        server_tools: response.server_tools || [],
        service_id: response.service_id || undefined,
        sandbox_service_id: response.sandbox_service_id || undefined,
        silo_id: response.silo_id || undefined,
        output_parser_id: response.output_parser_id || undefined,
        temperature: response.temperature ?? DEFAULT_AGENT_TEMPERATURE,
        tool_ids: response.tool_ids || [],
        mcp_config_ids: response.mcp_config_ids || [],
        skill_ids: response.skill_ids || [],
        middleware_ids: response.middleware_ids || [],
        // OCR-specific fields
        vision_service_id: response.vision_service_id || undefined,
        vision_system_prompt: response.vision_system_prompt || '',
        text_system_prompt: response.text_system_prompt || '',
        // RAG retrieval config
        rag_k: response.rag_k ?? 10,
        rag_search_type: response.rag_search_type ?? 'similarity',
        rag_score_threshold: response.rag_score_threshold ?? null,
        rag_max_retrieval_calls: response.rag_max_retrieval_calls ?? 4,
        rag_fixed_filters: (response.rag_fixed_filters ?? []).map((f) => ({
          ...f,
          _key: randomId(),
        })),
        // Media processing configuration
        transcription_service_id: response.transcription_service_id || undefined,
        video_ai_service_id: response.video_ai_service_id || undefined,
        media_embedding_service_id: response.media_embedding_service_id || undefined,
        media_forced_language: response.media_forced_language || '',
        media_chunk_min_duration: response.media_chunk_min_duration ?? 30,
        media_chunk_max_duration: response.media_chunk_max_duration ?? 120,
        media_chunk_overlap: response.media_chunk_overlap ?? 5,
        // A2A (Agent2Agent protocol) exposure
        a2a_enabled: response.a2a_enabled ?? false,
        a2a_card_visibility: response.a2a_card_visibility ?? 'public',
        a2a_name_override: response.a2a_name_override ?? null,
        a2a_description_override: response.a2a_description_override ?? null,
        a2a_skill_tags: response.a2a_skill_tags ?? [],
        a2a_examples: response.a2a_examples ?? [],
      });
      setA2aCardUrl(response.a2a_card_url ?? null);
      setA2aRpcUrl(response.a2a_rpc_url ?? null);

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
              conversation_starters: profile.conversation_starters?.map(s => s.prompt) || [],
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

  const handleA2AChange = useCallback((patch: Partial<AgentA2AValue>) => {
    setFormData(prev => ({ ...prev, ...patch }));
  }, []);

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
    },
    [],
  );

  const handleSaveMarketplaceProfile = useCallback(async () => {
    if (!appId || !agentId || Number.parseInt(agentId) === 0) return;

    const profileToSave: MarketplaceProfileUpdate = {
      display_name: marketplaceProfile.display_name,
      short_description: marketplaceProfile.short_description,
      long_description: marketplaceProfile.long_description,
      category: marketplaceProfile.category,
      tags: marketplaceProfile.tags,
      icon_url: marketplaceProfile.icon_url,
      cover_image_url: marketplaceProfile.cover_image_url,
      conversation_starters: (
        marketplaceProfile.conversation_starters ?? []
      )
        .map((starter) => starter.trim())
        .filter((starter) => starter.length > 0),
    };

    const saved = await mutate(
      () =>
        apiService.updateAgentMarketplaceProfile(
          Number.parseInt(appId),
          Number.parseInt(agentId),
          profileToSave,
        ),
      {
        loading: MESSAGES.SAVING('marketplace profile'),
        success: 'Marketplace profile saved',
        error: (err) => errorMessage(err, MESSAGES.SAVE_FAILED('marketplace profile')),
      },
    );

    if (saved === undefined) return;

    setMarketplaceProfile({
      display_name: saved.display_name || null,
      short_description: saved.short_description || null,
      long_description: saved.long_description || null,
      category: saved.category || null,
      tags: saved.tags || null,
      icon_url: saved.icon_url || null,
      cover_image_url: saved.cover_image_url || null,
      conversation_starters: saved.conversation_starters?.map(s => s.prompt) || [],
    });
  }, [appId, agentId, marketplaceProfile, mutate]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!appId || !agentId) return;

    const hasSilo = !!formData.silo_id;
    const usesThreshold = formData.rag_search_type === 'similarity_score_threshold';

    // The template is formatted with the user message; without {question} the message is lost.
    if (!formData.prompt_template.includes(DEFAULT_PROMPT_TEMPLATE)) {
      setActiveTab('prompts');
      setError('The Prompt Template must include {question} before saving.');
      return;
    }

    // Mirror the backend invariant: a threshold strategy needs a threshold value.
    if (usesThreshold && formData.rag_score_threshold == null) {
      setActiveTab('configuration');
      setError(SCORE_THRESHOLD_REQUIRED_MSG);
      return;
    }

    // Mirror the backend invariant: conversational agents keep uploaded documents in a
    // per-conversation temp silo, which needs an embedding service.
    if (formData.has_memory && !formData.media_embedding_service_id) {
      setActiveTab('configuration');
      setError('Conversational agents require a media embedding service in Media Processing.');
      return;
    }

    // Drop incomplete filter rows and the editor-only _key; clear the threshold unless the
    // threshold strategy is selected so we never persist a dead value.
    const cleanedFilters: RagFixedFilter[] = formData.rag_fixed_filters
      .filter((f) => f.field && (Array.isArray(f.value) ? f.value.length > 0 : String(f.value ?? '').trim() !== ''))
      .map(({ _key, ...rest }) => rest);

    // The A2A tab is disabled for new agents, so only existing agents send these
    // fields; a2a_card_visibility must never be sent as null (422 on the backend).
    const isExistingAgent = Number.parseInt(agentId) !== 0;
    const a2aFields = isExistingAgent
      ? {
          a2a_enabled: formData.a2a_enabled,
          a2a_card_visibility: formData.a2a_card_visibility,
          a2a_name_override: formData.a2a_name_override,
          a2a_description_override: formData.a2a_description_override,
          a2a_skill_tags: formData.a2a_skill_tags,
          a2a_examples: formData.a2a_examples.map((example) => example.trim()).filter((example) => example.length > 0),
        }
      : {};

    const submitData = {
      name: formData.name,
      description: formData.description,
      system_prompt: formData.system_prompt,
      prompt_template: formData.prompt_template,
      type: formData.type,
      is_tool: formData.is_tool,
      has_memory: formData.has_memory,
      enable_code_interpreter: formData.enable_code_interpreter,
      skill_router_enabled: formData.skill_router_enabled,
      server_tools: formData.server_tools,
      service_id: formData.service_id,
      sandbox_service_id: formData.enable_code_interpreter ? formData.sandbox_service_id : undefined,
      silo_id: formData.silo_id,
      output_parser_id: formData.output_parser_id,
      temperature: formData.temperature,
      tool_ids: formData.tool_ids,
      mcp_config_ids: formData.mcp_config_ids,
      skill_ids: formData.skill_ids,
      middleware_ids: formData.middleware_ids,
      // OCR-specific fields
      vision_service_id: formData.vision_service_id,
      vision_system_prompt: formData.vision_system_prompt,
      text_system_prompt: formData.text_system_prompt,
      // RAG retrieval config (full-replace; only meaningful with a silo)
      rag_k: formData.rag_k,
      rag_search_type: formData.rag_search_type,
      rag_score_threshold: usesThreshold ? formData.rag_score_threshold : null,
      rag_max_retrieval_calls: formData.rag_max_retrieval_calls,
      rag_fixed_filters: hasSilo ? cleanedFilters : [],
      // Media processing configuration
      transcription_service_id: formData.transcription_service_id,
      video_ai_service_id: formData.video_ai_service_id,
      media_embedding_service_id: formData.media_embedding_service_id,
      media_forced_language: formData.media_forced_language || undefined,
      media_chunk_min_duration: formData.media_chunk_min_duration,
      media_chunk_max_duration: formData.media_chunk_max_duration,
      media_chunk_overlap: formData.media_chunk_overlap,
      app_id: Number.parseInt(appId),
      ...a2aFields,
    };

    const isNew = Number.parseInt(agentId) === 0;

    // Save the marketplace profile first, but only once the form is valid, and
    // wait for it so it never races with the agent save below.
    await handleSaveMarketplaceProfile();

    setError(null);
    setA2aFieldErrors({});
    setSaving(true);

    // Created once so both the toast (via `mutate`) and our own error inspection
    // below observe the same settled promise instead of issuing the request twice.
    const submitPromise = isNew
      ? apiService.createAgent(Number.parseInt(appId), 0, submitData)
      : apiService.updateAgent(Number.parseInt(appId), Number.parseInt(agentId), submitData);

    const result = await mutate(() => submitPromise, {
      loading: isNew ? MESSAGES.CREATING('agent') : MESSAGES.UPDATING('agent'),
      success: isNew ? MESSAGES.CREATED('agent') : MESSAGES.UPDATED('agent'),
      error: (err) => errorMessage(err, MESSAGES.SAVE_FAILED('agent')),
    });
    setSaving(false);

    if (result !== undefined) {
      navigate(`/apps/${appId}/agents`);
      return;
    }

    try {
      await submitPromise;
    } catch (err) {
      const a2aErrors = extractA2AFieldErrors(err);
      if (a2aErrors) {
        setActiveTab('a2a');
        setA2aFieldErrors(a2aErrors);
      }
      // Keep the existing top-level banner in addition to the per-field messages.
      setError(errorMessage(err, MESSAGES.SAVE_FAILED('agent')));
    }
  };

  const isNewAgent = Number.parseInt(agentId || '0') === 0;

  if (loading) {
    return (
      <LoadingState variant="page" message="Loading agent..." />
    );
  }

  const pageTitle = getPageTitle(formData.type, isNewAgent);
  const pageDescription = getPageDescription(formData.type, isNewAgent, agent?.name);
  let submitButtonLabel: string;
  if (saving) {
    submitButtonLabel = 'Saving...';
  } else if (isNewAgent) {
    submitButtonLabel = 'Create Agent';
  } else {
    submitButtonLabel = 'Save Changes';
  }

  const tabs: TabItem[] = [
    { id: 'basic', label: 'Basic' },
    { id: 'prompts', label: 'Prompts' },
    { id: 'configuration', label: 'Configuration' },
    { id: 'advanced', label: 'Advanced' },
    { id: 'marketplace', label: 'Marketplace' },
    {
      id: 'a2a',
      label: 'A2A',
      disabled: isNewAgent,
      disabledReason: isNewAgent ? 'Save the agent first to configure A2A settings' : undefined,
    },
    ...(!isNewAgent ? [{ id: 'metrics', label: 'Metrics' }] : []),
  ];

  const videoServiceOptions = agent?.ai_services?.filter((service) => service.supports_video);

  return (
    <div className="min-h-screen p-6">
      <div className="max-w-4xl mx-auto">
        {/* Page Header */}
        <div className="flex items-center justify-between mb-8">
          {/*<div>
            <h1 className="text-3xl font-bold text-fg dark:text-fg-dark">
              {pageTitle}
            </h1>
            <p className="text-gray-600 mt-2">
              {pageDescription}
            </p>
          </div>*/}
          <Title
            titulo={pageTitle}
            subtitulo={pageDescription}
            variant="titPrincipal"
            subtitleMarginBottom={0}
          />
          {/*<button
            onClick={() => navigate(`/apps/${appId}/agents`)}
            className="flex items-center px-6 py-3 bg-white hover:bg-gray-50 rounded-xl text-fg-secondary dark:text-fg-secondary-dark shadow-sm border border-gray-200 transition-all duration-200"
          >
            <ArrowLeft className="w-4 h-4 mr-2" />
            {' '}
            Back to Agents
          </button>*/}
        </div>

        {agent && (
          <ServiceLifecycleAlert warnings={agent.lifecycle_warnings} variant="full" className="mb-6" />
        )}

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
          {!isNewAgent && agent && <ScheduledTaskReference appId={Number.parseInt(appId ?? '0')} agentId={agent.agent_id} />}

          {/* TAB 1: BASIC */}
          {activeTab === 'basic' && (
            <section className="">
              {/*<div className="mb-7 flex items-center gap-3 border-b border-line pb-5 dark:border-line-dark">
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-surface-hover dark:bg-surface-hover-dark">
                  <FileText className="h-5 w-5 text-ink dark:text-ink-dark" aria-hidden="true" />
                </div>
                <div>
                  <h3 className="font-display text-lg font-medium text-ink dark:text-ink-dark">Basic Information</h3>
                  <p className="mt-1 text-sm text-fg-secondary dark:text-fg-secondary-dark">Agent identity and type</p>
                </div>
              </div>*/}

              <div className="grid grid-cols-1 gap-y-5">
                <div className="w-full">
                <FormField
                  label="Name"
                  id="name"
                  value={formData.name}
                  onChange={(e) => handleInputChange('name', e.target.value)}
                  required
                  placeholder="Name..."
                  className="mb-4"
                />

                <FormSelect
                  label="Agent Type"
                  id="type"
                  value={formData.type}
                  onChange={(e) => handleInputChange('type', e.target.value)}
                  options={[
                    { value: 'agent', label: 'AI Agent' },
                    { value: 'ocr_agent', label: 'OCR Agent' },
                  ]}
                  className="mb-4"
                />

                <FormField
                  label="Description"
                  id="description"
                  value={formData.description}
                  onChange={(e) => handleInputChange('description', e.target.value)}
                  placeholder="Description..."
                  className="md:col-span-2"
                />
              </div>
              </div>
            </section>
          )}

          {/* TAB 2: PROMPTS */}
          {activeTab === 'prompts' && (
            <CardApp variant="white" className="p-8" icon={MessageSquare} titulo="Prompts & Instructions">
              <div className="space-y-6">
                <FormTextArea
                  label="System Prompt"
                  id="system_prompt"
                  value={formData.system_prompt}
                  onChange={(e) => handleInputChange('system_prompt', e.target.value)}
                  rows={4}
                  placeholder="Define the agent's behavior and capabilities..."
                />

                <div>
                  <FormTextArea
                    label="Prompt Template"
                    id="prompt_template"
                    value={formData.prompt_template}
                    onChange={(e) => handleInputChange('prompt_template', e.target.value)}
                    rows={4}
                    placeholder="Template for user interactions (must include {question})..."
                  />
                  <p className="text-xs text-fg-tertiary dark:text-fg-tertiary-dark mt-2 flex items-center gap-1"><Lightbulb className="w-3 h-3" /> The template must include {'{question}'} to work properly</p>
                </div>
              </div>
            </CardApp>
          )}

          {/* TAB 3: CONFIGURATION */}
          {activeTab === 'configuration' && (
            <div className="space-y-6">
              {/* Configuration for regular agents */}
              {formData.type !== 'ocr_agent' && (
                <>
                  <CardApp variant="white" className="p-8" icon={Settings} titulo="Configuration">
                    {/* No AI Services Warning */}
                    {agent?.ai_services.length === 0 && renderNoAIServicesWarning(false)}

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                      <div>
                        <FormSelect
                          label="AI Service"
                          id="ai_service"
                          ariaDescribedBy={serviceStatusId(agent?.ai_services, formData.service_id, "ai_service")}
                          value={formData.service_id || ''}
                          onChange={(e) => handleInputChange('service_id', e.target.value ? Number.parseInt(e.target.value) : undefined)}
                          required
                          options={[
                            { value: '', label: 'Select AI Service' },
                            ...selectableServiceOptions(agent?.ai_services, agent?.service_id).map((service) => ({
                              value: service.service_id,
                              label: serviceOptionLabel(service),
                            })),
                          ]}
                        />
                        <ServiceOptionStatus selectId="ai_service" options={agent?.ai_services} selectedId={formData.service_id} />
                      </div>

                      <div>
                        <FormSelect
                          label="Knowledge Base (Silo)"
                          id="silo"
                          value={formData.silo_id || ''}
                          onChange={(e) => handleInputChange('silo_id', e.target.value ? Number.parseInt(e.target.value) : undefined)}
                          options={[
                            { value: '', label: 'Select Knowledge Base' },
                            ...(agent?.silos.map((silo) => ({
                              value: silo.silo_id,
                              label: silo.name,
                            })) ?? []),
                          ]}
                        />
                      </div>

                      <div>
                        <label htmlFor="temperature" className="block text-sm font-medium text-fg-secondary dark:text-fg-secondary-dark mb-2">
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
                            className="flex-1 h-2 bg-gray-200 rounded-lg appearance-none accent-accent cursor-pointer"
                          />
                          <span className="text-sm font-medium text-fg-tertiary dark:text-fg-tertiary-dark w-12">
                            {formData.temperature.toFixed(1)}
                          </span>
                        </div>
                        <p className="text-xs text-fg-tertiary dark:text-fg-tertiary-dark mt-1">
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
                  </CardApp>

                  {/* RAG retrieval config — only meaningful when a silo is selected */}
                  {formData.silo_id && (
                    <RagConfigSection
                      value={{
                        rag_k: formData.rag_k,
                        rag_search_type: formData.rag_search_type,
                        rag_score_threshold: formData.rag_score_threshold,
                        rag_max_retrieval_calls: formData.rag_max_retrieval_calls,
                        rag_fixed_filters: formData.rag_fixed_filters,
                      }}
                      onChange={(patch: Partial<RagConfigValue>) =>
                        setFormData((prev) => ({ ...prev, ...patch }))
                      }
                      metadataFields={siloMetadataFields}
                      loadingMetadata={loadingSiloMetadata}
                    />
                  )}

                  {/* Agent Capabilities Card */}
                  <CardApp variant="white" className="p-8" icon={Zap} titulo="Capabilities">
                    {/* MCP Warning Dialog */}
                    {showMcpWarning && mcpUsage && mcpUsage.mcp_servers.length > 0 && (
                      <Alert
                        type="warning"
                        title={`This agent is used in ${mcpUsage.mcp_servers.length} MCP server${mcpUsage.mcp_servers.length === 1 ? '' : 's'}`}
                        className="mb-6"
                        message={(
                          <>
                            <span className="mb-2 block">
                              Unmarking this agent as a tool will make it unavailable in the following MCP servers:
                            </span>
                            <ul className="list-disc list-inside mb-3">
                              {mcpUsage.mcp_servers.map(s => (
                                <li key={s.server_id}>{s.server_name}</li>
                              ))}
                            </ul>
                            <span className="flex space-x-3">
                              <ButtonApp
                                label="Unmark as Tool Anyway"
                                variant="primary"
                                size="control"
                                onClick={() => {
                                  handleInputChange('is_tool', false);
                                  setShowMcpWarning(false);
                                }}
                              />
                              <ButtonApp
                                label="Cancel"
                                variant="secondary"
                                size="control"
                                onClick={() => setShowMcpWarning(false)}
                              />
                            </span>
                          </>
                        )}
                      />
                    )}

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                      <ButtonCard
                        variant="selectable-check"
                        selected={formData.is_tool}
                        ariaLabel="Toggle Tool Agent"
                        checkboxLabel="Tool Agent"
                        checkboxHelpText="Can be used by other agents"
                        onClick={() => {
                          if (formData.is_tool && mcpUsage && mcpUsage.mcp_servers.length > 0) {
                            setShowMcpWarning(true);
                          } else {
                            handleInputChange('is_tool', !formData.is_tool);
                          }
                        }}
                      >
                        {mcpUsage && mcpUsage.mcp_servers.length > 0 && formData.is_tool && (
                          <p className="ml-7 mt-1 text-xs text-fg-tertiary dark:text-fg-tertiary-dark">
                            Used in {mcpUsage.mcp_servers.length} MCP server{mcpUsage.mcp_servers.length === 1 ? '' : 's'}
                          </p>
                        )}
                      </ButtonCard>

                      <ButtonCard
                        variant="selectable-check"
                        selected={formData.has_memory}
                        ariaLabel="Toggle Conversational"
                        checkboxLabel="Conversational"
                        checkboxHelpText="Maintains conversation memory"
                        onClick={() => handleInputChange('has_memory', !formData.has_memory)}
                      />

                      <ButtonCard
                        variant="selectable-check"
                        selected={formData.enable_code_interpreter}
                        ariaLabel="Toggle Code Interpreter"
                        checkboxLabel="Code Interpreter"
                        checkboxHelpText="Allows the agent to execute Python code (pandas, openpyxl, numpy)"
                        onClick={() => handleInputChange('enable_code_interpreter', !formData.enable_code_interpreter)}
                      />

                      <ButtonCard
                        variant="selectable-check"
                        selected={formData.skill_router_enabled}
                        ariaLabel="Toggle Skill Router"
                        checkboxLabel="Skill Router"
                        checkboxHelpText="Let the model pre-select at most 2 skills per turn; off by default."
                        onClick={() => handleInputChange('skill_router_enabled', !formData.skill_router_enabled)}
                      />

                      {formData.enable_code_interpreter && (
                        <div className="md:col-span-2">
                          <FormSelect
                            label="Sandbox Service"
                            id="sandbox_service"
                            ariaDescribedBy={serviceStatusId(agent?.sandbox_services, formData.sandbox_service_id, 'sandbox_service')}
                            value={formData.sandbox_service_id || ''}
                            onChange={(e) => handleInputChange('sandbox_service_id', e.target.value ? Number.parseInt(e.target.value) : undefined)}
                            options={[
                              { value: '', label: 'Use app/system default' },
                              ...selectableServiceOptions(agent?.sandbox_services, agent?.sandbox_service_id).map((service) => ({
                                value: service.service_id,
                                label: serviceOptionLabel(service),
                              })),
                            ]}
                            helpText="Overrides the sandbox environment used to run this agent's Python code. Leave unset to use the app's default Sandbox Service."
                          />
                          <ServiceOptionStatus selectId="sandbox_service" options={agent?.sandbox_services} selectedId={formData.sandbox_service_id} />
                        </div>
                      )}
                    </div>

                    {/* Provider-side Tools */}
                    <div className="mt-6 pt-6 border-t border-line dark:border-btCard-border-dark">
                      <div className="mb-3">
                        <h4 className="text-sm font-semibold text-fg dark:text-fg-dark">Provider-side Tools</h4>
                        <p className="text-xs text-fg-tertiary dark:text-fg-tertiary-dark mt-0.5">
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
                              ? formData.server_tools.filter(t => t !== tool.id)
                              : [...formData.server_tools, tool.id]
                          );
                          return (
                            <ButtonCard
                              key={tool.id}
                              variant="selectable"
                              selected={active}
                              ariaLabel={`Toggle ${tool.label}`}
                              onClick={toggle}
                            >
                              <div className="flex items-center gap-2 mb-1">
                                <span className="text-base">{tool.icon}</span>
                                <span className={`text-sm font-medium ${active ? 'text-fg-primary dark:text-fg-primary-dark' : 'text-fg-tertiary dark:text-fg-tertiary-dark'}`}>
                                  {tool.label}
                                </span>
                                {active && (
                                  <span className="ml-auto text-xs font-medium bg-fg dark:bg-fg-dark text-ink-on dark:text-ink-on-dark shadow-sm px-1.5 py-0.5 rounded-full">ON</span>
                                )}
                              </div>
                              <p className="text-xs text-fg-tertiary dark:text-fg-tertiary-dark mb-2">{tool.description}</p>
                              <div className="flex flex-wrap gap-1">
                                {tool.providers.map(p => (
                                  <ProviderBadge key={p} provider={p} />
                                ))}
                              </div>
                            </ButtonCard>
                          );
                        })}
                      </div>
                      <Alert
                        type="warning"
                        title="Model compatibility"
                        className="my-1"
                        message="Some tools require specific models — e.g. Image Generation needs gpt-image-1 (OpenAI Responses API). Unsupported tools for the selected provider are silently ignored."
                      />
                    </div>
                  </CardApp>

                  {/* Media Processing Card */}
                  <CardApp
                    className="p-8"
                    icon={Tv}
                    titulo="Media Processing"
                    subtitulo="Default configuration used when uploading audio/video or YouTube URLs in the playground. Set it here once so uploads only require choosing the file or URL."
                  >
                    <div className="mb-6">
                      <FormSelect
                        label="Embedding Service"
                        id="media_embedding_service"
                        ariaDescribedBy={serviceStatusId(embeddingServices, formData.media_embedding_service_id, "media_embedding_service")}
                        required={formData.has_memory}
                        value={formData.media_embedding_service_id || ''}
                        onChange={(e) => handleInputChange('media_embedding_service_id', e.target.value ? Number.parseInt(e.target.value) : undefined)}
                        options={[
                          { value: '', label: 'None (no temporary knowledge base)' },
                          ...selectableServiceOptions(embeddingServices, agent?.media_embedding_service_id).map((service) => ({
                            value: service.service_id,
                            label: serviceOptionLabel(service),
                          })),
                        ]}
                        helpText="Model used to vectorize uploaded media/documents into the conversation's temporary knowledge base for retrieval. Required for conversational agents; optional otherwise (documents are then sent in full to the agent, and audio/video uploads are unavailable)."
                      />
                      <ServiceOptionStatus selectId="media_embedding_service" options={embeddingServices} selectedId={formData.media_embedding_service_id} />
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                      <div>
                        <FormSelect
                          label="Transcription Service"
                          id="transcription_service"
                          ariaDescribedBy={serviceStatusId(agent?.ai_services, formData.transcription_service_id, "transcription_service")}
                          value={formData.transcription_service_id || ''}
                          onChange={(e) => handleInputChange('transcription_service_id', e.target.value ? Number.parseInt(e.target.value) : undefined)}
                          options={[
                            { value: '', label: 'Select Transcription Service' },
                            ...selectableServiceOptions(agent?.ai_services, agent?.transcription_service_id).map((service) => ({
                              value: service.service_id,
                              label: serviceOptionLabel(service),
                            })),
                          ]}
                          helpText="Speech-to-text model used to transcribe media."
                        />
                        <ServiceOptionStatus selectId="transcription_service" options={agent?.ai_services} selectedId={formData.transcription_service_id} />
                      </div>

                      <div>
                        <FormSelect
                          label="Video Analysis Service (optional)"
                          id="video_ai_service"
                          ariaDescribedBy={serviceStatusId(videoServiceOptions, formData.video_ai_service_id, "video_ai_service")}
                          value={formData.video_ai_service_id || ''}
                          onChange={(e) => handleInputChange('video_ai_service_id', e.target.value ? Number.parseInt(e.target.value) : undefined)}
                          options={[
                            { value: '', label: 'None (audio only)' },
                            ...selectableServiceOptions(videoServiceOptions, agent?.video_ai_service_id).map((service) => ({
                              value: service.service_id,
                              label: serviceOptionLabel(service),
                            })),
                          ]}
                          helpText="Enables multimodal analysis (visual descriptions from video frames)."
                        />
                        <ServiceOptionStatus selectId="video_ai_service" options={videoServiceOptions} selectedId={formData.video_ai_service_id} />
                      </div>

                      <div>
                        <FormSelect
                          label="Language"
                          id="media_forced_language"
                          value={formData.media_forced_language || ''}
                          onChange={(e) => handleInputChange('media_forced_language', e.target.value || undefined)}
                          options={[
                            { value: '', label: 'Auto-detect' },
                            { value: 'es', label: 'Spanish' },
                            { value: 'en', label: 'English' },
                            { value: 'eu', label: 'Basque' },
                            { value: 'fr', label: 'French' },
                          ]}
                        />
                      </div>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mt-6">
                      <FormField
                        label="Min Chunk (s)"
                        id="media_chunk_min_duration"
                        type="number"
                        min={10}
                        max={60}
                        value={formData.media_chunk_min_duration}
                        onChange={(e) => handleInputChange('media_chunk_min_duration', Number.parseInt(e.target.value) || 30)}
                      />
                      <FormField
                        label="Max Chunk (s)"
                        id="media_chunk_max_duration"
                        type="number"
                        min={60}
                        max={300}
                        value={formData.media_chunk_max_duration}
                        onChange={(e) => handleInputChange('media_chunk_max_duration', Number.parseInt(e.target.value) || 120)}
                      />
                      <FormField
                        label="Overlap (s)"
                        id="media_chunk_overlap"
                        type="number"
                        min={0}
                        max={20}
                        value={formData.media_chunk_overlap}
                        onChange={(e) => handleInputChange('media_chunk_overlap', Number.parseInt(e.target.value) || 5)}
                      />
                    </div>
                  </CardApp>
                </>
              )}
              {/* Configuration for OCR agents */}
              {formData.type === 'ocr_agent' && (
                <CardApp   className="p-8">
                  <div className="flex items-center mb-6">
                    <BackgroundImage icon={FileText} size={40} iconSize={20} className='mr-2'/>
                      <h3 className="text-lg font-semibold text-fg dark:text-fg-dark">OCR Configuration</h3>
                  </div>

                  {/* Agent Capabilities Card for OCR agents — Tool Agent checkbox */}
                  <CardApp variant="canvas" className="p-6 mb-6">
                    <div className="flex items-center mb-4">
                      <BackgroundImage icon={Zap} size={40} iconSize={20} className='mr-2'/>
                      <h4 className="text-base font-semibold text-fg dark:text-fg-dark">Capabilities</h4>
                    </div>
                    <div className="space-y-4">
                      <ButtonCard
                        variant="selectable-check"
                        selected={formData.is_tool}
                        ariaLabel="Toggle Tool Agent"
                        checkboxLabel="Tool Agent"
                        checkboxHelpText="Can be used by other agents (including OCR tools)"
                        onClick={() => {
                          if (formData.is_tool && mcpUsage && mcpUsage.mcp_servers.length > 0) {
                            setShowMcpWarning(true);
                          } else {
                            handleInputChange('is_tool', !formData.is_tool);
                          }
                        }}
                        className="w-full"
                      >
                        {mcpUsage && mcpUsage.mcp_servers.length > 0 && formData.is_tool && (
                          <p className="ml-7 mt-1 text-xs text-fg-tertiary dark:text-fg-tertiary-dark">
                            Used in {mcpUsage.mcp_servers.length} MCP server{mcpUsage.mcp_servers.length === 1 ? '' : 's'}
                          </p>
                        )}
                      </ButtonCard>
                    </div>
                  </CardApp>

                  {/* No AI Services Warning */}
                  {agent?.ai_services.length === 0 && renderNoAIServicesWarning(true)}

                  <div className="space-y-6">
                    <div>
                      <FormSelect
                        label="Modelo de Visión"
                        id="vision_service"
                        ariaDescribedBy={serviceStatusId(agent?.ai_services, formData.vision_service_id, "vision_service")}
                        value={formData.vision_service_id || ''}
                        onChange={(e) => handleInputChange('vision_service_id', e.target.value ? Number.parseInt(e.target.value) : undefined)}
                        options={[
                          { value: '', label: '-- Seleccionar modelo de visión --' },
                          ...selectableServiceOptions(agent?.ai_services, agent?.vision_service_id).map((service) => ({
                            value: service.service_id,
                            label: serviceOptionLabel(service),
                          })),
                        ]}
                      />
                      <ServiceOptionStatus selectId="vision_service" options={agent?.ai_services} selectedId={formData.vision_service_id} />
                    </div>

                    <div>
                      <FormTextArea
                        label="System Prompt (Visión)"
                        id="vision_system_prompt"
                        value={formData.vision_system_prompt || ''}
                        onChange={(e) => handleInputChange('vision_system_prompt', e.target.value)}
                        rows={2}
                        placeholder="Añade el system prompt para el modelo de visión..."
                      />
                    </div>

                    <div>
                      <FormSelect
                        label="Modelo de Texto"
                        id="text_service"
                        ariaDescribedBy={serviceStatusId(agent?.ai_services, formData.service_id, "text_service")}
                        value={formData.service_id || ''}
                        onChange={(e) => handleInputChange('service_id', e.target.value ? Number.parseInt(e.target.value) : undefined)}
                        options={[
                          { value: '', label: '-- Seleccionar modelo de texto --' },
                          ...selectableServiceOptions(agent?.ai_services, agent?.service_id).map((service) => ({
                            value: service.service_id,
                            label: serviceOptionLabel(service),
                          })),
                        ]}
                      />
                      <ServiceOptionStatus selectId="text_service" options={agent?.ai_services} selectedId={formData.service_id} />
                    </div>

                    <div>
                      <FormTextArea
                        label="System Prompt (Texto)"
                        id="text_system_prompt"
                        value={formData.text_system_prompt || ''}
                        onChange={(e) => handleInputChange('text_system_prompt', e.target.value)}
                        rows={2}
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
                </CardApp>
              )}
            </div>
          )}

          {/* TAB 4: ADVANCED */}
          {activeTab === 'advanced' && (
            <div className="space-y-6">
              {/* Tools Card - Only for regular agents */}
              {agent && agent.tools.length > 0 && formData.type !== 'ocr_agent' && (
                <CardApp
                  className="p-8"
                  icon={Wrench}
                  titulo="Available Tools"
                  headerExtra={formData.tool_ids.length > 0 && (
                    <span className="text-sm text-fg-secondary dark:text-fg-secondary-dark">
                      <span className="font-medium">{formData.tool_ids.length}</span>{' '}
                      tool{formData.tool_ids.length === 1 ? '' : 's'} selected
                    </span>
                  )}
                >
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    {agent.tools.map((tool) => {
                      const selected = formData.tool_ids.includes(tool.agent_id);
                      return (
                        <ButtonCard
                          key={tool.agent_id}
                          variant="selectable-check"
                          selected={selected}
                          ariaLabel={`Toggle ${tool.name}`}
                          checkboxLabel={tool.name}
                          onClick={() => handleToolToggle(tool.agent_id)}
                          className="w-full"
                        />
                      );
                    })}
                  </div>
                </CardApp>
              )}

              {/* MCP Configs Card - Only for regular agents */}
              {agent?.mcp_configs && formData.type !== 'ocr_agent' && (
                <CardApp
                  variant="white"
                  icon={Plug}
                  titulo="MCP Servers"
                  headerExtra={(
                    <div className="flex items-center gap-3">
                      {formData.mcp_config_ids.length > 0 && (
                        <span className="text-sm text-fg-secondary dark:text-fg-secondary-dark">
                          <span className="font-medium">{formData.mcp_config_ids.length}</span>{' '}
                          MCP server{formData.mcp_config_ids.length === 1 ? '' : 's'} selected
                        </span>
                      )}
                      <Badge variant="primary" label="Model Context Protocol" />
                    </div>
                  )}
                >
                  {agent.mcp_configs.length > 0 ? (
                    <>
                      <Alert
                        type="info"
                        title="What are MCP Servers?"
                        message={'MCP (Model Context Protocol) servers allow agents to connect to external tools and data sources.\nSelect the servers this agent should have access to.'}
                        className="mb-4"
                      />
                      
                      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                        {agent.mcp_configs.map((mcp) => (
                          <ButtonCard
                            key={mcp.config_id}
                            variant="selectable-check"
                            selected={formData.mcp_config_ids.includes(mcp.config_id)}
                            ariaLabel={`Toggle ${mcp.name}`}
                            checkboxLabel={mcp.name}
                            onClick={() => handleMCPToggle(mcp.config_id)}
                            className="w-full"
                          />
                        ))}
                      </div>
                    </>
                  ) : (
                    <div className="text-center py-8">
                      <BackgroundImage icon={Plug} size={64} rounded="rounded-full" className=' flex items-center justify-center mx-auto mb-4'/>
                      <h4 className="text-lg font-medium text-fg dark:text-fg-dark mb-2">No MCP Servers Available</h4>
                      <p className="text-fg-tertiary dark:text-fg-tertiary-dark mb-4">
                        You haven't configured any MCP servers yet. Create MCP configurations in the settings to enable external tool access.
                      </p>
                      <ButtonApp
                        label="Configure MCP Servers"
                        onClick={() => navigate(`/apps/${appId}/settings/mcp-configs`)}
                        variant="primary"
                        size="medium"
                        icon={<Settings className="w-4 h-4" />}
                      />
                    </div>
                  )}
                </CardApp>
              )}

              {/* Middlewares Card - Only for regular agents */}
              {agent?.middlewares && formData.type !== 'ocr_agent' && (
                <AgentMiddlewaresCard
                  middlewares={agent.middlewares}
                  selectedIds={formData.middleware_ids}
                  hasMemory={formData.has_memory}
                  onChange={(ids) => setFormData((prev) => ({ ...prev, middleware_ids: ids }))}
                  onRequireMemory={() => setFormData((prev) => ({ ...prev, has_memory: true }))}
                  onManage={() => navigate(`/apps/${appId}/middlewares`)}
                />
              )}

              {/* Skills Card - Only for regular agents */}
              {agent?.skills && formData.type !== 'ocr_agent' && (
                <CardApp
                  className="p-8"
                  icon={Target}
                  titulo="Skills"
                  subtitulo="Assign specialized behaviors that the agent can activate on-demand"
                >
                  {agent.skills.length > 0 ? (
                    <>
                      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                        {agent.skills.map((skill) => {
                          const selected = formData.skill_ids.includes(skill.skill_id);
                          const checkboxHelpText = [
                            skill.description,
                            skill.is_system ? 'System skill.' : undefined,
                            skill.is_enabled === false ? 'Disabled; ignored at execution until re-enabled.' : undefined,
                          ].filter(Boolean).join(' ') || undefined;
                          return (
                            <ButtonCard
                              key={skill.skill_id}
                              onClick={() => handleSkillToggle(skill.skill_id)}
                              ariaLabel={`Toggle ${skill.name}`}
                              variant="selectable-check"
                              selected={selected}
                              checkboxLabel={skill.name}
                              checkboxHelpText={checkboxHelpText}
                              className="w-full"
                            >
                              {skill.is_system && (
                                <Badge label="System" variant="info" className="mt-2 self-start" />
                              )}
                              {skill.is_enabled === false && (
                                <Badge
                                  label="Disabled — ignored at execution until re-enabled"
                                  variant="warning"
                                  icon={<AlertTriangle className="w-3 h-3" aria-hidden="true" />}
                                  className="mt-2 self-start"
                                />
                              )}
                            </ButtonCard>
                          );
                        })}
                      </div>

                      {formData.skill_ids.length > 0 && (
                        <div className="mt-4 rounded-md border border-line bg-surface-hover p-4 dark:border-line-dark dark:bg-surface-hover-dark">
                          <p className="text-sm text-fg-secondary dark:text-fg-secondary-dark">
                            <span className="font-medium">{formData.skill_ids.length}</span> skill{formData.skill_ids.length === 1 ? '' : 's'} selected.
                            The agent will have a <code className="rounded bg-surface-ash px-1 dark:bg-surface-dark">load_skill</code> tool to activate these skills.
                          </p>
                        </div>
                      )}
                    </>
                  ) : (
                    <div className="text-center py-8">
                      <BackgroundImage icon={Target} size={64} rounded="rounded-full" className=' flex items-center justify-center mx-auto mb-4'/>
                      <h4 className="text-lg font-medium text-fg dark:text-fg-dark mb-2">No Skills Available</h4>
                      <p className="text-fg-tertiary dark:text-fg-tertiary-dark mb-4">
                        You haven't created any skills yet. Create skills in the settings to enable specialized agent behaviors.
                      </p>
                      <ButtonApp
                        label="Manage Skills"
                        onClick={() => navigate(`/apps/${appId}/skills`)}
                        variant="primary"
                        size="medium"
                        icon={<Target className="w-4 h-4" />}
                      />
                    </div>
                  )}
                </CardApp>
              )}
            </div>
          )}

          {/* TAB 5: MARKETPLACE */}
          {activeTab === 'marketplace' && (
            <CardApp className="p-8 mb-8" icon={Store} titulo="Marketplace Publishing">
              {/* New agent: prompt user to save first */}
              {isNewAgent ? (
                <Alert
                  type="info"
                  title="Agent not saved"
                  className="mb-8"
                  message="Save the agent first to configure marketplace publishing."
                />
              ) : (
              <>
              {/* Visibility Control */}
              <div className="mb-6">
                <div className="flex items-center gap-4">
                  <FormSelect
                    label="Marketplace Visibility"
                    id="marketplace-visibility"
                    value={marketplaceVisibility}
                    onChange={(e) => handleVisibilityChange(e.target.value as MarketplaceVisibility)}
                    disabled={formData.is_tool}
                    options={[
                      { value: 'unpublished', label: 'Unpublished (not listed)' },
                      { value: 'private', label: 'Private (visible to app members only)' },
                      { value: 'public', label: 'Public (visible to all users)' },
                    ]}
                    className="w-fit"
                    
                  />
                  {formData.is_tool && (
                    <span className="text-xs text-fg-tertiary dark:text-fg-tertiary-dark ml-2">Tool agents cannot be published to the marketplace</span>
                  )}
                </div>
              </div>
              {/* Profile Metadata (expandable) */}
              {showMarketplace && (
                <div className="space-y-6">
                  <FormField
                    label="Display Name"
                    id="marketplace-display-name"
                    value={marketplaceProfile.display_name ?? ''}
                    onChange={(e) => handleMarketplaceProfileChange('display_name', e.target.value)}
                    maxLength={255}
                    placeholder="Defaults to agent name if empty"
                  />
                  <FormTextArea
                    label="Short Description"
                    id="marketplace-short-description"
                    value={marketplaceProfile.short_description ?? ''}
                    onChange={(e) => handleMarketplaceProfileChange('short_description', e.target.value)}
                    maxLength={200}
                    rows={2}
                    helpText={`${marketplaceProfile.short_description?.length ?? 0}/200 characters`}
                  />
                  <FormTextArea
                    label="Long Description"
                    id="marketplace-long-description"
                    value={marketplaceProfile.long_description ?? ''}
                    onChange={(e) => handleMarketplaceProfileChange('long_description', e.target.value)}
                    rows={4}
                    placeholder="Supports Markdown"
                  />
                  <FormSelect
                    label="Category"
                    id="marketplace-category"
                    value={marketplaceProfile.category ?? ''}
                    onChange={(e) => handleMarketplaceProfileChange('category', e.target.value)}
                    options={[
                      { value: '', label: '-- Select a category --' },
                      ...MARKETPLACE_CATEGORIES.map((category) => ({
                        value: category,
                        label: category,
                      })),
                    ]}
                  />
                  <div>
                    <label htmlFor="marketplace-tags" className="block text-sm font-medium text-fg dark:text-fg-dark mb-2">Tags</label>
                    <TagInput
                      id="marketplace-tags"
                      tags={marketplaceProfile.tags ?? []}
                      onChange={(tags) => handleMarketplaceProfileChange('tags', tags)}
                      maxTags={5}
                      placeholder="Add up to 5 tags"
                    />
                  </div>
                    <FormField
                      label="Icon URL"
                      id="marketplace-icon-url"
                      value={marketplaceProfile.icon_url ?? ''}
                      onChange={(e) => handleMarketplaceProfileChange('icon_url', e.target.value)}
                      placeholder="https://..."
                    />
                    {marketplaceProfile.icon_url && (
                      <img
                        src={marketplaceProfile.icon_url}
                        alt="Icon preview"
                        className="mt-2 w-10 h-10 rounded"
                        onError={(e) => (e.currentTarget.style.display = 'none')}
                      />
                    )}
                    <FormField
                      label="Cover Image URL"
                      id="marketplace-cover-image-url"
                      value={marketplaceProfile.cover_image_url ?? ''}
                      onChange={(e) => handleMarketplaceProfileChange('cover_image_url', e.target.value)}
                      placeholder="https://..."
                    />
                    {marketplaceProfile.cover_image_url && (
                      <img
                        src={marketplaceProfile.cover_image_url}
                        alt="Cover preview"
                        className="mt-2 w-32 h-16 rounded object-cover"
                        onError={(e) => (e.currentTarget.style.display = 'none')}
                      />
                    )}
                   <div>
                     <label className="block text-sm font-medium text-fg-secondary dark:text-fg-secondary-dark mb-3">Conversation Starters</label>
                     <p className="text-xs text-fg-tertiary dark:text-fg-tertiary-dark mb-4">
                       Suggested opening messages for users. These only appear at the start of a new conversation.
                     </p>
                     <div className="space-y-3">
                       {marketplaceProfile.conversation_starters?.map((starter, idx) => (
                         <div key={idx} className="flex items-center gap-2">
                           <FormField
                             ref={(el) => {
                               starterRefs.current[idx] = el;
                             }}
                             label={`Conversation starter ${idx + 1}`}
                             id={`marketplace-conversation-starter-${idx}`}
                             value={starter}
                             onChange={(e) => {
                               const newStarters = [...(marketplaceProfile.conversation_starters || [])];
                               newStarters[idx] = e.target.value;
                               handleMarketplaceProfileChange('conversation_starters', newStarters);
                             }}
                             className="flex-1"
                             labelClassName="sr-only"
                             inputClassName="px-4 py-2"
                             placeholder="Enter a starter prompt..."
                           />
                           <button
                             type="button"
                             onClick={() => {
                               const newStarters = marketplaceProfile.conversation_starters?.filter((_, i) => i !== idx) || [];
                               handleMarketplaceProfileChange('conversation_starters', newStarters);
                             }}
                             className="p-2 text-red-500 hover:bg-red-50 rounded-lg transition-colors"
                           >
                             <span className="text-xs font-bold">✕</span>
                           </button>
                         </div>
                       ))}
                       <ButtonApp
                         label="Add Starter"
                         onClick={() => {
                           const newStarters = [...(marketplaceProfile.conversation_starters || []), ''];
                           handleMarketplaceProfileChange('conversation_starters', newStarters);
                           requestAnimationFrame(() => {
                             starterRefs.current[newStarters.length - 1]?.focus();
                           });
                         }}
                         variant="secondary"
                         size="medium"
                         icon={<Plus className="w-4 h-4" />}
                       />
                     </div>
                   </div>
                </div>
              )}
              </>
              )}
            </CardApp>
          )}

          {activeTab === 'a2a' && !isNewAgent && (
            <AgentA2ASettings
              appId={Number.parseInt(appId ?? '0')}
              value={{
                a2a_enabled: formData.a2a_enabled,
                a2a_card_visibility: formData.a2a_card_visibility,
                a2a_name_override: formData.a2a_name_override,
                a2a_description_override: formData.a2a_description_override,
                a2a_skill_tags: formData.a2a_skill_tags,
                a2a_examples: formData.a2a_examples,
              }}
              onChange={handleA2AChange}
              cardUrl={a2aCardUrl}
              rpcUrl={a2aRpcUrl}
              disabled={!canEditA2A}
              fieldErrors={a2aFieldErrors}
            />
          )}

          {activeTab === 'metrics' && !isNewAgent && (
            <div>
              <AgentMetricsTab
                appId={Number(appId)}
                agentId={Number(agentId)}
              />
            </div>
          )}

          {/* Form Actions */}
          <FormActions
            onCancel={() => navigate(`/apps/${appId}/agents`)}
            isSubmitting={saving}
            submitLabel={submitButtonLabel}
            containerClassName="mt-8 pt-6"
          />
        </form>
      </div>
    </div>
  );
}

export default AgentFormPage;
