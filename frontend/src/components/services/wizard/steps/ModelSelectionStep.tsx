import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ExternalLink, Filter, Search } from 'lucide-react';
import { FormField } from '../../../ui/FormField';
import Alert from '../../../ui/Alert';
import { Badge } from '../../../ui/Badge';
import { ButtonApp } from '../../../ui/ButtonApp';
import { ButtonCard } from '../../../ui/ButtonCard';
import { useProviderModels } from '../../../../hooks/useProviderModels';
import { getProviderDescriptor } from '../providers';
import type {
  ProviderModelInfo,
  ServiceKind,
  ServiceScope,
} from '../../../../types/services';
import type { CredentialsState } from './CredentialsStep';
import { Skeleton } from '../../../ui/Skeleton';

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

const FILTER_OPTIONS: readonly { id: CapabilityFilter; labelKey: string }[] = [
  { id: 'vision', labelKey: 'vision' },
  { id: 'function_calling', labelKey: 'functionCalling' },
  { id: 'reasoning', labelKey: 'reasoning' },
  { id: 'audio', labelKey: 'audio' },
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
  const { t } = useTranslation('common');
  const descriptor = getProviderDescriptor(provider);
  const [search, setSearch] = useState('');
  const [activeFilters, setActiveFilters] = useState<readonly CapabilityFilter[]>([]);

  const request = descriptor?.supportsModelListing
    ? {
        provider,
        api_key: credentials.api_key,
        base_url: credentials.base_url,
        api_version: credentials.api_version || undefined,
        aws_access_key_id: credentials.aws_access_key_id?.trim() || undefined,
        aws_region: credentials.aws_region?.trim() || undefined,
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
    let manualHelpKey = 'manualHelp.default';
    let manualFieldLabelKey = 'modelId';
    let manualPlaceholder = 'sentence-transformers/all-MiniLM-L6-v2';
    if (provider === 'Azure') {
      manualHelpKey = 'manualHelp.azure';
      manualFieldLabelKey = 'deploymentName';
      manualPlaceholder = 'my-gpt-4o-deployment';
    } else if (provider === 'GoogleCloud') {
      if (kind === 'embedding') {
        manualHelpKey = 'manualHelp.googleCloudEmbedding';
        manualPlaceholder = 'gemini-embedding-2-preview';
      } else {
        manualHelpKey = 'manualHelp.googleCloud';
        manualPlaceholder = 'gemini-2.5-pro';
      }
    }

    return (
      <div className="space-y-4">
        <div>
          <h3 className="text-base font-semibold text-fg dark:text-fg-dark">{t('serviceWizard.modelStep.modelIdentifier')}</h3>
          <p className="text-sm text-fg-secondary dark:text-fg-secondary-dark mt-1">{t(`serviceWizard.modelStep.${manualHelpKey}`)}</p>
        </div>
        <FormField
          label={t(`serviceWizard.modelStep.${manualFieldLabelKey}`)}
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
          title={t('serviceWizard.modelStep.noModelsTitle')}
          message={t('serviceWizard.modelStep.noModelsMessage')}
        />
        <FormField
          label={t('serviceWizard.modelStep.modelId')}
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
        <h3 className="text-base font-semibold text-fg dark:text-fg-dark">{t('serviceWizard.modelStep.chooseModel')}</h3>
        <p className="text-sm text-fg-secondary dark:text-fg-secondary-dark mt-1">
          {t('serviceWizard.modelStep.availableModels', {
            count: data.models.length,
            visibleCount: filteredModels.length,
            provider: descriptor?.label || provider,
          })}
        </p>
      </div>

      <div className="flex flex-col sm:flex-row gap-3">
        <div className="flex-1 relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-fg-faint dark:text-fg-faint-dark pointer-events-none" />
          <FormField
            id="model-search"
            type="text"
            ariaLabel={t('serviceWizard.modelStep.search')}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={t('serviceWizard.modelStep.search')}
            inputClassName="pl-9 pr-3"
          />
        </div>
        {kind === 'ai' && (
          <div className="flex flex-wrap gap-2">
            {FILTER_OPTIONS.map((f) => {
              const active = activeFilters.includes(f.id);
              return (
                <ButtonApp
                  key={f.id}
                  label={t(`serviceWizard.modelStep.filters.${f.labelKey}`)}
                  onClick={() => toggleFilter(f.id)}
                  icon={<Filter className="w-4 h-4" aria-hidden="true" />}
                  variant="muted"
                  size="medium"
                  ariaPressed={active}
                  className={`rounded-full ${active ? '' : 'opacity-60'}`}
                />
              );
            })}
          </div>
        )}
      </div>

      {filteredModels.length === 0 ? (
        <p className="text-sm text-fg-secondary dark:text-fg-secondary-dark italic px-2 py-8 text-center">
          {t('serviceWizard.modelStep.noMatches')}
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
  const { t } = useTranslation('common');
  const recent = isRecent(model.created_at);
  return (
    <ButtonCard
      variant="selectable"
      selected={selected}
      ariaLabel={t('serviceWizard.modelStep.selectModel', { model: model.display_name })}
      onClick={onSelect}
    >
      <div className="space-y-1">
        <div className="flex items-start justify-between gap-2">
          <span className="text-sm font-semibold text-gray-900 leading-tight line-clamp-2">
            {model.display_name}
          </span>
          <div className="flex flex-wrap gap-1 flex-shrink-0">
            {recent && (
              <Badge label={t('serviceWizard.modelStep.new')} variant="success" className="uppercase" />
            )}
            {model.deprecated && (
              <Badge label={t('serviceWizard.modelStep.deprecated')} variant="warning" className="uppercase" />
            )}
          </div>
        </div>
        <p className="text-xs font-mono text-fg-secondary dark:text-fg-secondary-dark truncate">{model.id}</p>
        <CapabilityChips info={model} />
        {model.context_window != null && (
          <p className="text-[11px] text-fg-secondary dark:text-fg-secondary-dark pt-0.5">
            {t('serviceWizard.modelStep.contextTokens', {
              count: model.context_window,
              formattedCount: Intl.NumberFormat().format(model.context_window),
            })}
          </p>
        )}
      </div>
    </ButtonCard>
  );
}

function CapabilityChips({ info }: { readonly info: ProviderModelInfo }) {
  const { t } = useTranslation('common');
  const chips: { labelKey: string; tone: string }[] = [];
  const c = info.capabilities;
  if (c.vision) chips.push({ labelKey: 'vision', tone: 'bg-purple-100 text-purple-800' });
  if (c.audio) chips.push({ labelKey: 'audio', tone: 'bg-orange-100 text-orange-800' });
  if (c.reasoning) chips.push({ labelKey: 'reasoning', tone: 'bg-indigo-100 text-indigo-800' });
  if (c.function_calling) chips.push({ labelKey: 'tools', tone: 'bg-blue-100 text-blue-800' });
  if (c.embedding) chips.push({ labelKey: 'embedding', tone: 'bg-green-100 text-green-800' });

  if (chips.length === 0) return null;

  return (
    <div className="flex flex-wrap gap-1 pt-1">
      {chips.map((chip) => (
        <span
          key={chip.labelKey}
          className={`text-[10px] font-medium px-1.5 py-0.5 rounded ${chip.tone}`}
        >
          {t(`serviceWizard.modelStep.capabilities.${chip.labelKey}`)}
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
        <Skeleton className="h-5 w-40" />
        <Skeleton className="h-4 w-64 mt-2" />
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {Array.from({ length: 6 }).map((_, idx) => (
          <div
            key={idx}
            className="p-3 rounded-lg border border-line bg-surface space-y-2 dark:border-line-dark dark:bg-surface-dark"
          >
            <Skeleton className="h-4 w-3/4" />
            <Skeleton className="h-3 w-1/2" />
            <div className="flex gap-1 pt-1">
              <Skeleton className="h-3 w-12" />
              <Skeleton className="h-3 w-10" />
            </div>
            <Skeleton className="h-3 w-20 mt-1" />
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
  const { t } = useTranslation('common');
  // 404 from a Custom OpenAI-compatible endpoint that doesn't expose
  // /models — fall back to manual entry inline.
  if (status === 404) {
    return (
      <div className="space-y-3">
        <Alert
          type="info"
          title={t('serviceWizard.modelStep.endpointNoModelsTitle')}
          message={t('serviceWizard.modelStep.endpointNoModelsMessage')}
        />
        <FormField
          label={t('serviceWizard.modelStep.modelId')}
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

  let titleKey = 'serviceWizard.modelStep.errors.loadFailed';
  let description = message;
  if (status === 401) {
    titleKey = 'serviceWizard.modelStep.errors.invalidApiKey';
    description = t('serviceWizard.modelStep.errors.invalidApiKeyMessage');
  } else if (status === 408) {
    titleKey = 'serviceWizard.modelStep.errors.timeout';
    description = t('serviceWizard.modelStep.errors.timeoutMessage');
  } else if (status === 502) {
    titleKey = 'serviceWizard.modelStep.errors.providerUnreachable';
    description = t('serviceWizard.modelStep.errors.providerUnreachableMessage');
  }

  return (
    <Alert
      type="error"
      title={t(titleKey)}
      message={(
        <>
          {description}
          <span className="mt-3 flex flex-wrap items-center gap-3">
            <ButtonApp label={t('serviceWizard.modelStep.errors.retry')} variant="danger" size="compact" onClick={onRetry} />
            {status === 401 && descriptorDocUrl && (
              <a
                href={descriptorDocUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-xs font-medium underline"
              >
                <ExternalLink className="w-3 h-3" />
                {t('serviceWizard.modelStep.errors.getProviderKey', { provider })}
              </a>
            )}
          </span>
        </>
      )}
    />
  );
}

export default ModelSelectionStep;
