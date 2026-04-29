import { useMemo, useState } from 'react';
import { ExternalLink, Search } from 'lucide-react';
import { FormField } from '../../../ui/FormField';
import Alert from '../../../ui/Alert';
import { useProviderModels } from '../../../../hooks/useProviderModels';
import { getProviderDescriptor } from '../providers';
import type {
  ProviderModelInfo,
  ServiceKind,
  ServiceScope,
} from '../../../../types/services';
import type { CredentialsState } from './CredentialsStep';

interface ModelSelectionStepProps {
  readonly kind: ServiceKind;
  readonly scope: ServiceScope;
  readonly appId?: number;
  readonly provider: string;
  readonly credentials: CredentialsState;
  readonly selected: ProviderModelInfo | null;
  readonly onSelect: (model: ProviderModelInfo) => void;
  readonly manualModelName: string;
  readonly onManualModelNameChange: (value: string) => void;
}

type CapabilityFilter = 'vision' | 'function_calling' | 'reasoning' | 'audio';

const FILTER_OPTIONS: readonly { id: CapabilityFilter; label: string }[] = [
  { id: 'vision', label: 'Vision' },
  { id: 'function_calling', label: 'Function calling' },
  { id: 'reasoning', label: 'Reasoning' },
  { id: 'audio', label: 'Audio' },
];

const SIXTY_DAYS_SECONDS = 60 * 24 * 60 * 60;

function isRecent(createdAt: number | null): boolean {
  if (createdAt == null) return false;
  const nowSeconds = Math.floor(Date.now() / 1000);
  return nowSeconds - createdAt < SIXTY_DAYS_SECONDS;
}

function ModelSelectionStep({
  kind,
  scope,
  appId,
  provider,
  credentials,
  selected,
  onSelect,
  manualModelName,
  onManualModelNameChange,
}: Readonly<ModelSelectionStepProps>) {
  const descriptor = getProviderDescriptor(provider);
  const [search, setSearch] = useState('');
  const [activeFilters, setActiveFilters] = useState<readonly CapabilityFilter[]>([]);

  const request = descriptor?.supportsModelListing
    ? {
        provider,
        api_key: credentials.api_key,
        base_url: credentials.base_url,
        api_version: credentials.api_version || undefined,
      }
    : null;

  const { data, loading, error, retry } = useProviderModels({
    kind,
    scope,
    appId,
    request,
    enabled: !!descriptor?.supportsModelListing,
  });

  const filteredModels = useMemo(() => {
    if (!data) return [];
    const needle = search.trim().toLowerCase();
    return data.models.filter((m) => {
      if (
        needle &&
        !m.id.toLowerCase().includes(needle) &&
        !m.display_name.toLowerCase().includes(needle)
      ) {
        return false;
      }
      for (const f of activeFilters) {
        if (!m.capabilities[f]) return false;
      }
      return true;
    });
  }, [data, search, activeFilters]);

  const toggleFilter = (id: CapabilityFilter) => {
    setActiveFilters((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    );
  };

  // ----- Manual input mode -----
  if (descriptor && !descriptor.supportsModelListing) {
    let manualHelp = 'Enter the model identifier you want to use.';
    if (provider === 'Azure') {
      manualHelp = 'Enter the deployment name configured in your Azure OpenAI resource.';
    } else if (provider === 'GoogleCloud') {
      manualHelp = 'Enter the Vertex AI model id you want to use.';
    }
    let manualPlaceholder = 'sentence-transformers/all-MiniLM-L6-v2';
    if (provider === 'Azure') manualPlaceholder = 'my-gpt-4o-deployment';
    else if (provider === 'GoogleCloud') manualPlaceholder = 'gemini-2.5-pro';

    return (
      <div className="space-y-4">
        <div>
          <h3 className="text-base font-semibold text-gray-900">Model identifier</h3>
          <p className="text-sm text-gray-600 mt-1">{manualHelp}</p>
        </div>
        <FormField
          label={provider === 'Azure' ? 'Deployment name' : 'Model id'}
          id="manual_model_name"
          type="text"
          value={manualModelName}
          onChange={(e) => onManualModelNameChange(e.target.value)}
          placeholder={manualPlaceholder}
          required
        />
      </div>
    );
  }

  if (loading) {
    return <ModelGridSkeleton />;
  }

  if (error) {
    return (
      <ProviderListingError
        status={error.status}
        message={error.message}
        provider={provider}
        descriptorDocUrl={descriptor?.apiKeyDocUrl}
        onRetry={retry}
        manualModelName={manualModelName}
        onManualModelNameChange={onManualModelNameChange}
      />
    );
  }

  if (!data || data.models.length === 0) {
    return (
      <div className="space-y-4">
        <Alert
          type="warning"
          title="No models returned"
          message="The provider returned an empty list. You can type a model id manually below if you know it."
        />
        <FormField
          label="Model id"
          id="manual_model_name_empty"
          type="text"
          value={manualModelName}
          onChange={(e) => onManualModelNameChange(e.target.value)}
          placeholder="model-id"
        />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-base font-semibold text-gray-900">Choose a model</h3>
        <p className="text-sm text-gray-600 mt-1">
          {filteredModels.length} of {data.models.length} model
          {data.models.length === 1 ? '' : 's'} available from{' '}
          {descriptor?.label || provider}. Newest models are shown first.
        </p>
      </div>

      <div className="flex flex-col sm:flex-row gap-3">
        <div className="flex-1 relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by id or name"
            className="w-full pl-9 pr-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
          />
        </div>
        {kind === 'ai' && (
          <div className="flex flex-wrap gap-2">
            {FILTER_OPTIONS.map((f) => {
              const active = activeFilters.includes(f.id);
              return (
                <button
                  key={f.id}
                  type="button"
                  onClick={() => toggleFilter(f.id)}
                  className={`px-3 py-1.5 text-xs font-medium rounded-full border transition-colors ${
                    active
                      ? 'bg-blue-600 text-white border-blue-600'
                      : 'bg-white text-gray-700 border-gray-300 hover:border-gray-400'
                  }`}
                >
                  {f.label}
                </button>
              );
            })}
          </div>
        )}
      </div>

      {filteredModels.length === 0 ? (
        <p className="text-sm text-gray-500 italic px-2 py-8 text-center">
          No models match your filters.
        </p>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 max-h-[480px] overflow-y-auto pr-1">
          {filteredModels.map((m) => (
            <ModelCard
              key={m.id}
              model={m}
              selected={selected?.id === m.id}
              onSelect={() => onSelect(m)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

interface ModelCardProps {
  readonly model: ProviderModelInfo;
  readonly selected: boolean;
  readonly onSelect: () => void;
}

function ModelCard({ model, selected, onSelect }: Readonly<ModelCardProps>) {
  const recent = isRecent(model.created_at);
  return (
    <button
      type="button"
      onClick={onSelect}
      className={`text-left p-3 rounded-lg border transition-all focus:outline-none focus:ring-2 focus:ring-blue-500 ${
        selected
          ? 'border-blue-600 ring-2 ring-blue-200 bg-blue-50'
          : 'border-gray-200 bg-white hover:border-gray-300 hover:shadow-sm'
      }`}
    >
      <div className="space-y-1">
        <div className="flex items-start justify-between gap-2">
          <span className="text-sm font-semibold text-gray-900 leading-tight line-clamp-2">
            {model.display_name}
          </span>
          <div className="flex flex-wrap gap-1 flex-shrink-0">
            {recent && (
              <span className="text-[10px] uppercase font-medium px-1.5 py-0.5 rounded bg-emerald-100 text-emerald-800">
                New
              </span>
            )}
            {model.deprecated && (
              <span className="text-[10px] uppercase font-medium px-1.5 py-0.5 rounded bg-amber-100 text-amber-800">
                Deprecated
              </span>
            )}
          </div>
        </div>
        <p className="text-xs font-mono text-gray-500 truncate">{model.id}</p>
        <CapabilityChips info={model} />
        {model.context_window != null && (
          <p className="text-[11px] text-gray-500 pt-0.5">
            {Intl.NumberFormat().format(model.context_window)} ctx tokens
          </p>
        )}
      </div>
    </button>
  );
}

function CapabilityChips({ info }: { readonly info: ProviderModelInfo }) {
  const chips: { label: string; tone: string }[] = [];
  const c = info.capabilities;
  if (c.vision) chips.push({ label: 'Vision', tone: 'bg-purple-100 text-purple-800' });
  if (c.audio) chips.push({ label: 'Audio', tone: 'bg-orange-100 text-orange-800' });
  if (c.reasoning) chips.push({ label: 'Reasoning', tone: 'bg-indigo-100 text-indigo-800' });
  if (c.function_calling) chips.push({ label: 'Tools', tone: 'bg-blue-100 text-blue-800' });
  if (c.embedding) chips.push({ label: 'Embedding', tone: 'bg-green-100 text-green-800' });

  if (chips.length === 0) return null;

  return (
    <div className="flex flex-wrap gap-1 pt-1">
      {chips.map((chip) => (
        <span
          key={chip.label}
          className={`text-[10px] font-medium px-1.5 py-0.5 rounded ${chip.tone}`}
        >
          {chip.label}
        </span>
      ))}
    </div>
  );
}

// ==================== Skeleton ====================

function ModelGridSkeleton() {
  return (
    <div className="space-y-4">
      <div>
        <div className="h-5 w-40 bg-gray-200 rounded animate-pulse" />
        <div className="h-4 w-64 mt-2 bg-gray-100 rounded animate-pulse" />
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {Array.from({ length: 6 }).map((_, idx) => (
          <div
            key={idx}
            className="p-3 rounded-lg border border-gray-200 bg-white space-y-2 animate-pulse"
          >
            <div className="h-4 w-3/4 bg-gray-200 rounded" />
            <div className="h-3 w-1/2 bg-gray-100 rounded" />
            <div className="flex gap-1 pt-1">
              <div className="h-3 w-12 bg-gray-100 rounded" />
              <div className="h-3 w-10 bg-gray-100 rounded" />
            </div>
            <div className="h-3 w-20 bg-gray-100 rounded mt-1" />
          </div>
        ))}
      </div>
    </div>
  );
}

// ==================== Error states with CTA ====================

interface ProviderListingErrorProps {
  readonly status: number | undefined;
  readonly message: string;
  readonly provider: string;
  readonly descriptorDocUrl?: string;
  readonly onRetry: () => void;
  readonly manualModelName: string;
  readonly onManualModelNameChange: (value: string) => void;
}

function ProviderListingError({
  status,
  message,
  provider,
  descriptorDocUrl,
  onRetry,
  manualModelName,
  onManualModelNameChange,
}: Readonly<ProviderListingErrorProps>) {
  // 404 from a Custom OpenAI-compatible endpoint that doesn't expose
  // /models — fall back to manual entry inline.
  if (status === 404) {
    return (
      <div className="space-y-3">
        <Alert
          type="info"
          title="Endpoint did not return a model list"
          message="Some self-hosted servers do not implement the Ollama tags endpoint or OpenAI's /models route. Type the model id manually below."
        />
        <FormField
          label="Model id"
          id="manual_model_name_fallback"
          type="text"
          value={manualModelName}
          onChange={(e) => onManualModelNameChange(e.target.value)}
          placeholder="my-model"
          required
        />
      </div>
    );
  }

  let title = 'Failed to load models';
  let description = message;
  if (status === 401) {
    title = 'Invalid API key';
    description =
      'The provider rejected your credentials. Double-check the key was copied without extra spaces and that it has the right permissions.';
  } else if (status === 408) {
    title = 'Request timed out';
    description =
      'The provider did not respond within 15 seconds. Check your network or the endpoint URL and retry.';
  } else if (status === 502) {
    title = 'Could not reach the provider';
    description =
      'A network error stopped the request. If you are using a self-hosted endpoint, verify the URL and that the service is running.';
  }

  return (
    <div className="rounded-lg border border-red-200 bg-red-50 p-4 space-y-3">
      <div>
        <h4 className="text-sm font-semibold text-red-800">{title}</h4>
        <p className="text-sm text-red-700 mt-1">{description}</p>
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={onRetry}
          className="px-3 py-1.5 text-xs font-medium bg-white text-red-800 border border-red-300 rounded hover:bg-red-100"
        >
          Retry listing
        </button>
        {status === 401 && descriptorDocUrl && (
          <a
            href={descriptorDocUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-xs font-medium text-red-800 hover:text-red-900"
          >
            <ExternalLink className="w-3 h-3" />
            Get a {provider} key
          </a>
        )}
      </div>
    </div>
  );
}

export default ModelSelectionStep;
