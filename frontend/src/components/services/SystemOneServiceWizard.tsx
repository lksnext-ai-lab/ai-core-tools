import { useEffect, useRef, useState } from 'react';
import { Trans, useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import { CheckCircle2, Loader2, Plug, RefreshCw, XCircle } from 'lucide-react';
import Modal from '../ui/Modal';
import { StepperContainer } from '../ui/Stepper';
import type { StepDefinition, StepStatus } from '../ui/Stepper';
import { FormField } from '../ui/FormField';
import Alert from '../ui/Alert';
import { apiService } from '../../services/api';
import { ensureUnique } from './wizard/ServiceWizard';
import ProviderStep from './wizard/steps/ProviderStep';
import { ModelCard } from './wizard/steps/ModelSelectionStep';
import { getProviderDescriptor } from './wizard/providers';
import ServiceLifecycleInputs from './ServiceLifecycleInputs';
import { checkConcurrency } from '../../utils/systemOneLimits';
import { dateInputValueFromIso, endOfServiceForSave } from '../../utils/serviceLifecycle';
import type { ProviderModelInfo } from '../../types/services';
import type {
  SystemOneConnectionResult,
  SystemOneProvider,
  SystemOneServiceDetail,
  SystemOneServicePayload,
} from '../../types/systemOne';

// Same shape as the AI service wizard: provider -> credentials -> model (listed from the API) -> confirm and test.
const STEP_IDS = ['provider', 'connection', 'model', 'test'] as const;

function buildSteps(t: TFunction): StepDefinition[] {
  return [
    { id: 'provider', label: t('serviceWizard.steps.provider') },
    { id: 'connection', label: t('systemOne.wizard.stepConnection') },
    { id: 'model', label: t('serviceWizard.steps.model') },
    { id: 'test', label: t('systemOne.wizard.stepTest') },
  ];
}

interface SystemOneServiceWizardProps {
  readonly isOpen: boolean;
  readonly appId: number;
  /** null = creating a new service. */
  readonly service: SystemOneServiceDetail | null;
  /** Names already used in the app, to suggest a free one. */
  readonly existingNames?: readonly string[];
  readonly onClose: () => void;
  readonly onSave: (payload: SystemOneServicePayload) => Promise<void> | void;
}

const normalizeUrl = (url: string) => url.trim().replace(/\/+$/, '').toLowerCase();
const isUrl = (url: string) => /^https?:\/\/\S+$/i.test(url.trim());

function limitsSummary(limits: Record<string, number> | null, t: TFunction): string | null {
  if (!limits) return null;
  const parts: string[] = [];
  if (limits.max_concurrent_requests != null) parts.push(t('systemOne.wizard.limitConcurrent', { count: limits.max_concurrent_requests }));
  if (limits.max_questions != null) parts.push(t('systemOne.wizard.limitQuestions', { count: limits.max_questions }));
  if (limits.max_prompt_tokens != null) parts.push(t('systemOne.wizard.limitTokens', { count: limits.max_prompt_tokens }));
  return parts.length ? parts.join(' · ') : null;
}

function errorResult(err: unknown, fallback: string): SystemOneConnectionResult {
  return { status: 'error', message: err instanceof Error ? err.message : fallback, models: [], limits: null };
}

function SystemOneServiceWizard({ isOpen, appId, service, existingNames = [], onClose, onSave }: SystemOneServiceWizardProps) {
  const { t } = useTranslation('common');
  const steps = buildSteps(t);
  const isEdit = service !== null && service.service_id !== 0;
  const [currentStep, setCurrentStep] = useState(0);
  const [stepStatuses, setStepStatuses] = useState<Record<string, StepStatus>>({});

  const [provider, setProvider] = useState<SystemOneProvider | ''>(service?.provider ?? '');
  const providerInfo = getProviderDescriptor(provider);
  const tokenRequired = providerInfo?.apiKey === 'required';
  const [endpoint, setEndpoint] = useState(service?.endpoint || '');
  const [apiKey, setApiKey] = useState(service?.api_key ?? '');
  const [tokenReset, setTokenReset] = useState(false);

  const [listing, setListing] = useState(false);
  const [listResult, setListResult] = useState<SystemOneConnectionResult | null>(null);
  const [model, setModel] = useState(service?.model ?? '');

  const [name, setName] = useState(service?.name ?? '');
  const [concurrency, setConcurrency] = useState<string>(service ? String(service.max_concurrency) : '');
  const [endOfServiceDate, setEndOfServiceDate] = useState(dateInputValueFromIso(service?.end_of_service_at));
  const [deprecationNotice, setDeprecationNotice] = useState(service?.deprecation_notice ?? '');
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<SystemOneConnectionResult | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const serviceId = isEdit ? service.service_id : undefined;
  const stepId = STEP_IDS[currentStep];
  const models = listResult?.status === 'success' ? listResult.models : [];
  const imageModels = listResult?.status === 'success' ? (listResult.image_models ?? []) : [];
  // The cards of the AI service wizard: only what the server tells is filled in (images -> "Vision", date -> "New").
  const toModelInfo = (id: string): ProviderModelInfo => ({
    id, display_name: id, family: null, context_window: null, owned_by: null, deprecated: false, source: 'api',
    created_at: (listResult?.status === 'success' ? listResult.created?.[id] : undefined) ?? null,
    capabilities: {
      chat: false, embedding: false, vision: imageModels.includes(id), audio: false,
      function_calling: false, tool_use: false, reasoning: false, json_mode: false,
    },
  });
  const listFailed = listResult !== null && models.length === 0;

  // The stored token belongs to the server it was typed for: moving the service empties the masked value
  // (the backend refuses to carry it over) and the user types it again if the new server needs one.
  function changeEndpoint(value: string) {
    setEndpoint(value);
    setListResult(null);
    if (isEdit && apiKey.startsWith('****') && normalizeUrl(value) !== normalizeUrl(service.endpoint)) {
      setApiKey('');
      setTokenReset(true);
    }
  }

  // Changing the provider swaps the URL only while it still is a provider default (never a URL the user typed), and
  // drops what depended on the previous one.
  function changeProvider(next: SystemOneProvider) {
    if (next === provider) return;
    const defaults = ['system_one', 'openai_decisions'].map((v) => normalizeUrl(getProviderDescriptor(v)?.defaultBaseUrl ?? ''));
    if (endpoint.trim() === '' || defaults.includes(normalizeUrl(endpoint))) {
      setEndpoint(getProviderDescriptor(next)?.defaultBaseUrl ?? '');
    }
    setProvider(next);
    setListResult(null);
    setModel('');
  }

  async function listModels() {
    setListing(true);
    setListResult(null);
    try {
      const result = await apiService.testSystemOneServiceWithConfig(
        appId, { endpoint: endpoint.trim(), api_key: apiKey.trim(), provider: provider as SystemOneProvider }, serviceId);
      setListResult(result);
      if (result.status === 'success' && result.suggested_max_concurrency != null && concurrency.trim() === '') {
        setConcurrency(String(result.suggested_max_concurrency));
      }
    } catch (err) {
      setListResult(errorResult(err, t('systemOne.wizard.listFailed')));
    } finally {
      setListing(false);
    }
  }

  // Entering the model step asks the server which models it offers (once per connection).
  const listedFor = useRef('');
  useEffect(() => {
    if (!isOpen || stepId !== 'model') return;
    const key = `${provider}|${endpoint.trim()}|${apiKey.trim()}`;
    if (listedFor.current === key) return;
    listedFor.current = key;
    void listModels();
  }, [isOpen, stepId]);

  const parsedConcurrency = concurrency.trim() === '' ? null : Number(concurrency);
  const concurrencyError =
    parsedConcurrency !== null && (!Number.isInteger(parsedConcurrency) || parsedConcurrency < 1)
      ? t('systemOne.wizard.concurrencyInvalid')
      : null;
  // The latest answer from the server (the model step or an explicit test) tells how many requests it accepts.
  const known = testResult?.status === 'success' ? testResult : listResult?.status === 'success' ? listResult : null;
  const concurrencyCheck = checkConcurrency(concurrencyError === null ? parsedConcurrency : null, known?.limits?.max_concurrent_requests);
  const suggestedName = ensureUnique(model.trim() ? `System One - ${model.trim()}` : 'System One', existingNames);
  const finalName = name.trim() || suggestedName;

  function nextDisabled(): boolean {
    if (stepId === 'provider') return !provider;
    if (stepId === 'connection') return !isUrl(endpoint) || (tokenRequired && !apiKey.trim());
    if (stepId === 'model') return listing || !model.trim();
    return !finalName || concurrencyError !== null || concurrencyCheck !== null;
  }

  function payload(): SystemOneServicePayload {
    return {
      name: finalName,
      endpoint: endpoint.trim(),
      provider: provider as SystemOneProvider,
      api_key: apiKey.trim(),
      model: model.trim(),
      max_concurrency: parsedConcurrency,
      // Always sent: an explicit null clears the date and the notice.
      end_of_service_at: endOfServiceForSave(service?.end_of_service_at, endOfServiceDate),
      deprecation_notice: deprecationNotice.trim() || null,
    };
  }

  async function handleTest() {
    setTesting(true);
    setTestResult(null);
    try {
      // The model goes along: a server that cannot list models is then checked with one real, tiny call.
      const result = await apiService.testSystemOneServiceWithConfig(
        appId, { endpoint: endpoint.trim(), api_key: apiKey.trim(), model: model.trim(), provider: provider as SystemOneProvider }, serviceId);
      // Reachable is not enough: the model that will be saved has to be one the server offers.
      if (result.status === 'success' && result.models.length > 0 && !result.models.includes(model.trim())) {
        setTestResult({ ...result, status: 'error', message: t('systemOne.wizard.modelNotOffered', { model: model.trim() }) });
      } else {
        setTestResult(result);
      }
    } catch (err) {
      setTestResult(errorResult(err, t('systemOne.wizard.testFailed')));
    } finally {
      setTesting(false);
    }
  }

  async function handleNext() {
    if (stepId === 'test') {
      setSubmitting(true);
      setSubmitError(null);
      try {
        await onSave(payload());
      } catch (err) {
        setSubmitError(err instanceof Error ? err.message : t('systemOne.wizard.saveFailed'));
      } finally {
        setSubmitting(false);
      }
      return;
    }
    // Anything edited upstream invalidates a previous test.
    setTestResult(null);
    setStepStatuses((prev) => ({ ...prev, [stepId]: 'completed' }));
    setCurrentStep((s) => Math.min(s + 1, STEP_IDS.length - 1));
  }

  function handleBack() {
    setStepStatuses((prev) => {
      const next = { ...prev };
      delete next[stepId];
      return next;
    });
    setCurrentStep((s) => Math.max(s - 1, 0));
  }

  // Limits are shown only for a result that succeeded: next to a failed test (token rejected, no connection) they would
  // contradict it. Before any test, the ones the model step already read are fine.
  const limits = limitsSummary(testResult ? (testResult.status === 'success' ? testResult.limits : null) : (listResult?.limits ?? null), t);

  return (
    <Modal isOpen={isOpen} onClose={onClose} title={isEdit ? t('systemOne.wizard.titleEdit') : t('systemOne.wizard.titleAdd')} size="xlarge">
      <div className="flex flex-col" style={{ minHeight: '420px' }}>
        <StepperContainer
          steps={steps}
          currentStep={currentStep}
          stepStatuses={stepStatuses}
          onNext={handleNext}
          onBack={handleBack}
          onCancel={onClose}
          nextDisabled={nextDisabled()}
          isSubmitting={submitting}
          nextLabel={stepId === 'test' ? (submitting ? t('systemOne.wizard.saving') : t('common.save')) : undefined}
          showBack
        >
          <div className="px-2 py-3">
            {stepId === 'provider' && (
              <ProviderStep kind="system_one" selected={provider} onSelect={(v) => changeProvider(v as SystemOneProvider)} />
            )}

            {stepId === 'connection' && (
              <div className="space-y-4">
                <div>
                  <h3 className="text-base font-semibold text-gray-900">{t('systemOne.wizard.connectTitle')}</h3>
                  <p className="text-sm text-gray-600 mt-1">
                    {t('systemOne.wizard.connectDescription')}
                  </p>
                </div>
                <FormField
                  label={t('systemOne.wizard.serverUrl')}
                  id="so-endpoint"
                  type="text"
                  value={endpoint}
                  onChange={(e) => changeEndpoint(e.target.value)}
                  placeholder={providerInfo?.baseUrlPlaceholder}
                  helpText={t('systemOne.wizard.serverUrlHelp')}
                  required
                />
                <FormField
                  label={tokenRequired ? t('systemOne.wizard.apiKey') : t('systemOne.wizard.tokenOptional')}
                  id="so-token"
                  type="password"
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  placeholder={providerInfo?.apiKeyPlaceholder}
                  required={tokenRequired}
                  helpText={isEdit && !tokenReset ? t('systemOne.wizard.keepMasked') : undefined}
                />
                {tokenReset && (
                  <Alert type="warning" message={t('systemOne.wizard.tokenCleared')} />
                )}
              </div>
            )}

            {stepId === 'model' && (
              <div className="space-y-4">
                <div>
                  <h3 className="text-base font-semibold text-gray-900">{t('systemOne.wizard.chooseModel')}</h3>
                  <p className="text-sm text-gray-600 mt-1">{t('systemOne.wizard.modelsOffered', { endpoint: endpoint.trim() })}</p>
                </div>
                {listing && (
                  <p className="flex items-center gap-2 text-sm text-gray-600" role="status">
                    <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> {t('systemOne.wizard.listing')}
                  </p>
                )}
                {!listing && listFailed && (
                  <>
                    <Alert
                      type="warning"
                      title={listResult?.status === 'error' ? t('systemOne.wizard.couldNotList') : t('systemOne.wizard.noModels')}
                      message={`${listResult?.status === 'error' ? `${listResult.message}. ` : ''}${t('systemOne.wizard.typeIdentifier')}`}
                    />
                    <FormField label={t('systemOne.wizard.modelIdentifier')} id="so-model-manual" type="text" value={model}
                               onChange={(e) => setModel(e.target.value)} placeholder="model-name" required />
                    <button type="button" onClick={() => void listModels()}
                            className="inline-flex items-center gap-2 rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-700 hover:bg-gray-50">
                      <RefreshCw className="h-4 w-4" aria-hidden="true" /> {t('systemOne.wizard.retry')}
                    </button>
                  </>
                )}
                {!listing && models.length > 0 && (
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 max-h-[480px] overflow-y-auto pr-1" role="group" aria-label={t('systemOne.wizard.modelsGroup')}>
                    {models.map((m) => (
                      <ModelCard key={m} model={toModelInfo(m)} selected={model === m} onSelect={() => setModel(m)} />
                    ))}
                  </div>
                )}
              </div>
            )}

            {stepId === 'test' && (
              <div className="space-y-4">
                <div>
                  <h3 className="text-base font-semibold text-gray-900">{t('systemOne.wizard.testTitle')}</h3>
                  <p className="text-sm text-gray-600 mt-1">
                    <Trans
                      i18nKey="systemOne.wizard.modelAtEndpoint"
                      t={t}
                      values={{ model: model.trim(), endpoint: endpoint.trim() }}
                      components={{ mono: <span className="font-mono" /> }}
                    />
                  </p>
                </div>
                <FormField label={t('common.name')} id="so-name" type="text" value={name} onChange={(e) => setName(e.target.value)}
                           placeholder={suggestedName} helpText={t('systemOne.wizard.nameHelp')} />
                <FormField
                  label={t('systemOne.wizard.concurrencyLabel')}
                  id="so-concurrency"
                  type="number"
                  value={concurrency}
                  onChange={(e) => setConcurrency(e.target.value)}
                  placeholder="1"
                  error={concurrencyError ?? concurrencyCheck ?? undefined}
                  helpText={
                    (listResult?.suggested_max_concurrency != null
                      ? `${t('systemOne.wizard.concurrencySuggested', { value: listResult.suggested_max_concurrency })} `
                      : '') +
                    t('systemOne.wizard.concurrencyHelp')
                  }
                />
                <div aria-live="polite">
                  {testResult && (
                    <div className={`rounded-lg p-3 text-sm ${testResult.status === 'success' ? 'bg-green-50 text-green-800' : 'bg-red-50 text-red-800'}`}>
                      <div className="flex items-center gap-2 font-medium">
                        {testResult.status === 'success'
                          ? <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
                          : <XCircle className="h-4 w-4" aria-hidden="true" />}
                        {testResult.message}
                      </div>
                      {limits && <p className="mt-1 text-xs">{t('systemOne.wizard.serverLimits', { limits })}</p>}
                    </div>
                  )}
                </div>
                {listResult?.status === 'success' && models.length === 0 && (
                  <p className="text-xs text-gray-500">
                    {t('systemOne.wizard.cannotListNote')}
                  </p>
                )}
                <button type="button" onClick={() => void handleTest()} disabled={testing}
                        className="inline-flex items-center gap-2 rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-700 hover:bg-gray-50 disabled:opacity-60">
                  {testing ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Plug className="h-4 w-4" aria-hidden="true" />}
                  {testing ? t('connectionTestResult.testingAction') : t('connectionTestResult.testConnection')}
                </button>

                <div className="mt-4">
                  <ServiceLifecycleInputs
                    date={endOfServiceDate}
                    notice={deprecationNotice}
                    onDateChange={setEndOfServiceDate}
                    onNoticeChange={setDeprecationNotice}
                  />
                </div>
              </div>
            )}

            {submitError && <p className="mt-3 text-sm text-red-600 px-2" role="alert">{submitError}</p>}
          </div>
        </StepperContainer>
      </div>
    </Modal>
  );
}

export default SystemOneServiceWizard;
