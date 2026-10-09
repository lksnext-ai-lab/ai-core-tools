import { useEffect, useRef, useState } from 'react';
import { CheckCircle2, Loader2, Plug, RefreshCw, XCircle } from 'lucide-react';
import Modal from '../ui/Modal';
import { StepperContainer } from '../ui/Stepper';
import type { StepDefinition, StepStatus } from '../ui/Stepper';
import { FormField } from '../ui/FormField';
import Alert from '../ui/Alert';
import { apiService } from '../../services/api';
import { SYSTEM_ONE_DEFAULT_ENDPOINT } from '../../types/systemOne';
import type {
  SystemOneConnectionResult,
  SystemOneServiceDetail,
  SystemOneServicePayload,
} from '../../types/systemOne';

// Same three-step shape as the AI service wizard: credentials -> model (listed from the API) -> confirm and test.
const STEPS: StepDefinition[] = [
  { id: 'connection', label: 'Connection' },
  { id: 'model', label: 'Model' },
  { id: 'test', label: 'Test' },
];

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

function ensureUnique(base: string, existing: readonly string[]): string {
  if (!existing.includes(base)) return base;
  let counter = 2;
  while (existing.includes(`${base} (${counter})`)) counter++;
  return `${base} (${counter})`;
}

function limitsSummary(limits: Record<string, number> | null): string | null {
  if (!limits) return null;
  const parts: string[] = [];
  if (limits.max_concurrent_requests != null) parts.push(`${limits.max_concurrent_requests} concurrent requests`);
  if (limits.max_questions != null) parts.push(`${limits.max_questions} questions per call`);
  if (limits.max_prompt_tokens != null) parts.push(`${limits.max_prompt_tokens} tokens per question`);
  return parts.length ? parts.join(' · ') : null;
}

function errorResult(err: unknown, fallback: string): SystemOneConnectionResult {
  return { status: 'error', message: err instanceof Error ? err.message : fallback, models: [], limits: null };
}

function SystemOneServiceWizard({ isOpen, appId, service, existingNames = [], onClose, onSave }: SystemOneServiceWizardProps) {
  const isEdit = service !== null && service.service_id !== 0;
  const [currentStep, setCurrentStep] = useState(0);
  const [stepStatuses, setStepStatuses] = useState<Record<string, StepStatus>>({});

  const [endpoint, setEndpoint] = useState(service?.endpoint || SYSTEM_ONE_DEFAULT_ENDPOINT);
  const [apiKey, setApiKey] = useState(service?.api_key ?? '');
  const [tokenReset, setTokenReset] = useState(false);

  const [listing, setListing] = useState(false);
  const [listResult, setListResult] = useState<SystemOneConnectionResult | null>(null);
  const [model, setModel] = useState(service?.model ?? '');

  const [name, setName] = useState(service?.name ?? '');
  const [concurrency, setConcurrency] = useState<string>(service ? String(service.max_concurrency) : '');
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<SystemOneConnectionResult | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const serviceId = isEdit ? service.service_id : undefined;
  const stepId = STEPS[currentStep].id;
  const models = listResult?.status === 'success' ? listResult.models : [];
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

  async function listModels() {
    setListing(true);
    setListResult(null);
    try {
      const result = await apiService.testSystemOneServiceWithConfig(
        appId, { endpoint: endpoint.trim(), api_key: apiKey.trim() }, serviceId);
      setListResult(result);
      if (result.status === 'success' && result.suggested_max_concurrency != null && concurrency.trim() === '') {
        setConcurrency(String(result.suggested_max_concurrency));
      }
    } catch (err) {
      setListResult(errorResult(err, 'Failed to list the models'));
    } finally {
      setListing(false);
    }
  }

  // Entering the model step asks the server which models it offers (once per connection).
  const listedFor = useRef('');
  useEffect(() => {
    if (!isOpen || stepId !== 'model') return;
    const key = `${endpoint.trim()}|${apiKey.trim()}`;
    if (listedFor.current === key) return;
    listedFor.current = key;
    void listModels();
  }, [isOpen, stepId]);

  const parsedConcurrency = concurrency.trim() === '' ? null : Number(concurrency);
  const concurrencyError =
    parsedConcurrency !== null && (!Number.isInteger(parsedConcurrency) || parsedConcurrency < 1)
      ? 'Enter a whole number of at least 1, or leave it empty'
      : null;
  const suggestedName = ensureUnique(model.trim() ? `System One - ${model.trim()}` : 'System One', existingNames);
  const finalName = name.trim() || suggestedName;

  function nextDisabled(): boolean {
    if (stepId === 'connection') return !isUrl(endpoint);
    if (stepId === 'model') return listing || !model.trim();
    return !finalName || concurrencyError !== null;
  }

  function payload(): SystemOneServicePayload {
    return {
      name: finalName,
      endpoint: endpoint.trim(),
      api_key: apiKey.trim(),
      model: model.trim(),
      max_concurrency: parsedConcurrency,
    };
  }

  async function handleTest() {
    setTesting(true);
    setTestResult(null);
    try {
      const result = await apiService.testSystemOneServiceWithConfig(
        appId, { endpoint: endpoint.trim(), api_key: apiKey.trim() }, serviceId);
      // Reachable is not enough: the model that will be saved has to be one the server offers.
      if (result.status === 'success' && result.models.length > 0 && !result.models.includes(model.trim())) {
        setTestResult({ ...result, status: 'error', message: `The server does not offer the model "${model.trim()}"` });
      } else {
        setTestResult(result);
      }
    } catch (err) {
      setTestResult(errorResult(err, 'Failed to test the connection'));
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
        setSubmitError(err instanceof Error ? err.message : 'Failed to save the service');
      } finally {
        setSubmitting(false);
      }
      return;
    }
    // Anything edited upstream invalidates a previous test.
    setTestResult(null);
    setStepStatuses((prev) => ({ ...prev, [stepId]: 'completed' }));
    setCurrentStep((s) => Math.min(s + 1, STEPS.length - 1));
  }

  function handleBack() {
    setStepStatuses((prev) => {
      const next = { ...prev };
      delete next[stepId];
      return next;
    });
    setCurrentStep((s) => Math.max(s - 1, 0));
  }

  const limits = limitsSummary(testResult?.limits ?? listResult?.limits ?? null);

  return (
    <Modal isOpen={isOpen} onClose={onClose} title={isEdit ? 'Edit System One service' : 'Add System One service'} size="xlarge">
      <div className="flex flex-col" style={{ minHeight: '420px' }}>
        <StepperContainer
          steps={STEPS}
          currentStep={currentStep}
          stepStatuses={stepStatuses}
          onNext={handleNext}
          onBack={handleBack}
          onCancel={onClose}
          nextDisabled={nextDisabled()}
          isSubmitting={submitting}
          nextLabel={stepId === 'test' ? (submitting ? 'Saving...' : 'Save') : undefined}
          showBack
        >
          <div className="px-2 py-3">
            {stepId === 'connection' && (
              <div className="space-y-4">
                <div>
                  <h3 className="text-base font-semibold text-gray-900">Connect to a System One server</h3>
                  <p className="text-sm text-gray-600 mt-1">
                    System One answers closed questions about a text with probabilities. These values are used to list
                    the available models. They are not saved until you confirm the service in the last step.
                  </p>
                </div>
                <FormField
                  label="Server URL"
                  id="so-endpoint"
                  type="text"
                  value={endpoint}
                  onChange={(e) => changeEndpoint(e.target.value)}
                  placeholder="https://your-system-one-host"
                  helpText="Private addresses are allowed: a self-hosted server normally lives on a private network."
                  required
                />
                <FormField
                  label="Token (optional)"
                  id="so-token"
                  type="password"
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  placeholder="Bearer token, if the server requires one"
                  helpText={isEdit && !tokenReset ? 'Leave the masked value to keep the stored token; empty it to remove it.' : undefined}
                />
                {tokenReset && (
                  <Alert type="warning" message="The URL changed, so the stored token was cleared: type it again if the new server needs one." />
                )}
              </div>
            )}

            {stepId === 'model' && (
              <div className="space-y-4">
                <div>
                  <h3 className="text-base font-semibold text-gray-900">Choose a model</h3>
                  <p className="text-sm text-gray-600 mt-1">The models offered by {endpoint.trim()}.</p>
                </div>
                {listing && (
                  <p className="flex items-center gap-2 text-sm text-gray-600" role="status">
                    <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> Asking the server for its models...
                  </p>
                )}
                {!listing && listFailed && (
                  <>
                    <Alert
                      type="warning"
                      title={listResult?.status === 'error' ? 'Could not list the models' : 'The server returned no models'}
                      message={`${listResult?.status === 'error' ? `${listResult.message}. ` : ''}You can type the model identifier below if you know it.`}
                    />
                    <FormField label="Model identifier" id="so-model-manual" type="text" value={model}
                               onChange={(e) => setModel(e.target.value)} placeholder="model-name" required />
                    <button type="button" onClick={() => void listModels()}
                            className="inline-flex items-center gap-2 rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-700 hover:bg-gray-50">
                      <RefreshCw className="h-4 w-4" aria-hidden="true" /> Retry
                    </button>
                  </>
                )}
                {!listing && models.length > 0 && (
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 max-h-[320px] overflow-y-auto pr-1" role="radiogroup" aria-label="Models">
                    {models.map((m) => (
                      <button
                        key={m}
                        type="button"
                        role="radio"
                        aria-checked={model === m}
                        onClick={() => setModel(m)}
                        className={`text-left p-3 rounded-lg border transition-colors ${
                          model === m ? 'border-blue-500 bg-blue-50 ring-1 ring-blue-500' : 'border-gray-200 bg-white hover:border-gray-300'
                        }`}
                      >
                        <span className="text-sm font-semibold text-gray-900 break-all">{m}</span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}

            {stepId === 'test' && (
              <div className="space-y-4">
                <div>
                  <h3 className="text-base font-semibold text-gray-900">Test and save</h3>
                  <p className="text-sm text-gray-600 mt-1">
                    <span className="font-mono">{model.trim()}</span> at <span className="font-mono">{endpoint.trim()}</span>
                  </p>
                </div>
                <FormField label="Name" id="so-name" type="text" value={name} onChange={(e) => setName(e.target.value)}
                           placeholder={suggestedName} helpText="Leave it empty to use the suggested name." />
                <FormField
                  label="Maximum concurrent requests (per backend process)"
                  id="so-concurrency"
                  type="number"
                  value={concurrency}
                  onChange={(e) => setConcurrency(e.target.value)}
                  placeholder="1"
                  error={concurrencyError ?? undefined}
                  helpText={
                    (listResult?.suggested_max_concurrency != null
                      ? `Suggested for this server: ${listResult.suggested_max_concurrency}. `
                      : '') +
                    'The server accepts a limited number of requests at once and answers 529 above it: use its limit divided by the number of backend processes.'
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
                      {limits && <p className="mt-1 text-xs">Server limits: {limits}</p>}
                    </div>
                  )}
                </div>
                <button type="button" onClick={() => void handleTest()} disabled={testing}
                        className="inline-flex items-center gap-2 rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-700 hover:bg-gray-50 disabled:opacity-60">
                  {testing ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Plug className="h-4 w-4" aria-hidden="true" />}
                  {testing ? 'Testing...' : 'Test connection'}
                </button>
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
