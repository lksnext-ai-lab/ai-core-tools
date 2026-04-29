import { useEffect, useMemo, useState } from 'react';
import Modal from '../../ui/Modal';
import { StepperContainer } from '../../ui/Stepper';
import type { StepDefinition, StepStatus } from '../../ui/Stepper';
import ProviderStep from './steps/ProviderStep';
import CredentialsStep, { type CredentialsState } from './steps/CredentialsStep';
import ModelSelectionStep from './steps/ModelSelectionStep';
import ConfirmStep from './steps/ConfirmStep';
import { getProviderDescriptor } from './providers';
import { getServiceApiClient } from '../serviceApi';
import type { TestConnectionResult } from '../serviceApi';
import type {
  ExistingService,
  ProviderModelInfo,
  ServiceFormData,
  ServiceKind,
  ServiceScope,
  ServiceWizardMode,
} from '../../../types/services';

const STEPS: StepDefinition[] = [
  { id: 'provider', label: 'Provider' },
  { id: 'credentials', label: 'Credentials' },
  { id: 'model', label: 'Model' },
  { id: 'confirm', label: 'Confirm' },
];

const EMPTY_CREDENTIALS: CredentialsState = {
  api_key: '',
  base_url: '',
  api_version: '',
};

interface ServiceWizardProps {
  readonly isOpen: boolean;
  readonly kind: ServiceKind;
  readonly scope: ServiceScope;
  readonly appId?: number;
  readonly mode?: ServiceWizardMode;
  /** When `mode === 'edit-model'`, the existing service to mutate. */
  readonly initialService?: ExistingService | null;
  /** Existing service names in scope, used to disambiguate auto-generated names. */
  readonly existingNames?: readonly string[];
  readonly onClose: () => void;
  readonly onSave: (data: ServiceFormData) => Promise<void>;
}

function ServiceWizard({
  isOpen,
  kind,
  scope,
  appId,
  mode = 'create',
  initialService = null,
  existingNames = [],
  onClose,
  onSave,
}: Readonly<ServiceWizardProps>) {
  const [provider, setProvider] = useState('');
  const [credentials, setCredentials] = useState<CredentialsState>(EMPTY_CREDENTIALS);
  const [selectedModel, setSelectedModel] = useState<ProviderModelInfo | null>(null);
  const [manualModelName, setManualModelName] = useState('');
  const [supportsVideo, setSupportsVideo] = useState(false);
  const [currentStep, setCurrentStep] = useState(0);
  const [stepStatuses, setStepStatuses] = useState<Record<string, StepStatus>>({});
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<TestConnectionResult | null>(null);

  // Reset every time the wizard re-opens.
  useEffect(() => {
    if (!isOpen) return;
    if (mode === 'edit-model' && initialService) {
      setProvider(initialService.provider || '');
      setCredentials({
        ...EMPTY_CREDENTIALS,
        // We never receive the real key — leave it blank so the user
        // re-enters it (required to list models again).
        api_key: '',
        base_url: initialService.base_url || '',
        api_version: initialService.api_version || '',
      });
      setManualModelName(initialService.model_name || '');
      setSupportsVideo(!!initialService.supports_video);
      setCurrentStep(1); // skip provider step in edit mode
      setStepStatuses({ provider: 'completed' });
    } else {
      setProvider('');
      setCredentials(EMPTY_CREDENTIALS);
      setSelectedModel(null);
      setManualModelName('');
      setSupportsVideo(false);
      setCurrentStep(0);
      setStepStatuses({});
    }
    setSubmitError(null);
    setSubmitting(false);
    setTesting(false);
    setTestResult(null);
  }, [isOpen, mode, initialService]);

  const descriptor = getProviderDescriptor(provider);

  const autoName = useMemo(() => {
    if (!provider) return '';
    const modelPart = descriptor?.supportsModelListing
      ? selectedModel?.display_name || selectedModel?.id || ''
      : manualModelName;
    if (!modelPart) return '';
    const base = `${descriptor?.label || provider} - ${modelPart}`;
    return ensureUnique(base, existingNames);
  }, [provider, descriptor, selectedModel, manualModelName, existingNames]);

  const stepDisabled = useMemo(() => {
    switch (STEPS[currentStep].id) {
      case 'provider':
        return !provider;
      case 'credentials':
        if (!descriptor) return true;
        if (descriptor.apiKey === 'required' && !credentials.api_key.trim()) return true;
        if (descriptor.needsBaseUrl && !credentials.base_url.trim()) return true;
        return false;
      case 'model':
        if (!descriptor?.supportsModelListing) return !manualModelName.trim();
        return !selectedModel;
      case 'confirm':
        return !autoName;
      default:
        return false;
    }
  }, [currentStep, provider, descriptor, credentials, selectedModel, manualModelName, autoName]);

  const handleNext = async () => {
    const stepId = STEPS[currentStep].id;
    if (stepId === 'confirm') {
      await handleSubmit();
      return;
    }
    // Any edit upstream of the confirm step invalidates a previous
    // test result — credentials or the selected model may have changed.
    setTestResult(null);
    setStepStatuses((prev) => ({ ...prev, [stepId]: 'completed' }));
    setCurrentStep((s) => Math.min(s + 1, STEPS.length - 1));
  };

  const handleBack = () => {
    setStepStatuses((prev) => {
      const next = { ...prev };
      const stepId = STEPS[currentStep].id;
      delete next[stepId];
      return next;
    });
    setCurrentStep((s) => Math.max(s - 1, 0));
  };

  const buildPayload = (): ServiceFormData => {
    const modelName = descriptor?.supportsModelListing
      ? selectedModel?.id || ''
      : manualModelName.trim();
    return {
      name: autoName || `${provider} - ${modelName}`,
      provider,
      model_name: modelName,
      api_key: credentials.api_key,
      base_url: credentials.base_url,
      api_version: credentials.api_version || undefined,
      supports_video: supportsVideo,
    };
  };

  const handleSubmit = async () => {
    setSubmitting(true);
    setSubmitError(null);
    try {
      await onSave(buildPayload());
      onClose();
    } catch (e) {
      setSubmitError(e instanceof Error ? e.message : 'Failed to save service');
    } finally {
      setSubmitting(false);
    }
  };

  const handleTest = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const client = getServiceApiClient(kind, scope, appId);
      setTestResult(await client.testConnection(buildPayload()));
    } catch (e) {
      setTestResult({
        status: 'error',
        message: e instanceof Error ? e.message : 'Test failed',
      });
    } finally {
      setTesting(false);
    }
  };

  let title = kind === 'ai' ? 'Add AI Service' : 'Add Embedding Service';
  if (mode === 'edit-model') title = 'Change model';

  return (
    <Modal isOpen={isOpen} onClose={onClose} title={title} size="xlarge">
      <div className="flex flex-col" style={{ minHeight: '500px' }}>
        <StepperContainer
          steps={STEPS}
          currentStep={currentStep}
          stepStatuses={stepStatuses}
          onNext={handleNext}
          onBack={handleBack}
          onCancel={onClose}
          nextDisabled={stepDisabled}
          isSubmitting={submitting}
          nextLabel={STEPS[currentStep].id === 'confirm' ? (submitting ? 'Saving...' : 'Save') : undefined}
          showBack={mode === 'create' || currentStep > 1}
        >
          <div className="px-2 py-3">
            {STEPS[currentStep].id === 'provider' && (
              <ProviderStep
                kind={kind}
                selected={provider}
                onSelect={(v) => {
                  if (v === provider) return;
                  setProvider(v);
                  // Reset everything that depends on the provider so
                  // values from the previous one (api_key, base_url,
                  // selected model, supports_video) don't leak across
                  // and confuse the listing call in the next step.
                  // Pre-fill base_url with the provider's default so
                  // the credentials step renders with a sensible value.
                  const next = getProviderDescriptor(v);
                  setCredentials({
                    ...EMPTY_CREDENTIALS,
                    base_url: next?.defaultBaseUrl ?? '',
                  });
                  setSelectedModel(null);
                  setManualModelName('');
                  setSupportsVideo(false);
                }}
              />
            )}
            {STEPS[currentStep].id === 'credentials' && (
              <CredentialsStep
                provider={provider}
                mode={mode}
                value={credentials}
                onChange={setCredentials}
              />
            )}
            {STEPS[currentStep].id === 'model' && (
              <ModelSelectionStep
                kind={kind}
                scope={scope}
                appId={appId}
                provider={provider}
                credentials={credentials}
                selected={selectedModel}
                onSelect={setSelectedModel}
                manualModelName={manualModelName}
                onManualModelNameChange={setManualModelName}
              />
            )}
            {STEPS[currentStep].id === 'confirm' && (
              <ConfirmStep
                kind={kind}
                provider={provider}
                model={selectedModel}
                manualModelName={manualModelName}
                autoName={autoName}
                credentials={credentials}
                supportsVideo={supportsVideo}
                onSupportsVideoChange={setSupportsVideo}
                onTest={handleTest}
                testing={testing}
                testResult={testResult}
              />
            )}
            {submitError && (
              <p className="mt-3 text-sm text-red-600 px-2" role="alert">
                {submitError}
              </p>
            )}
          </div>
        </StepperContainer>
      </div>
    </Modal>
  );
}

function ensureUnique(base: string, existing: readonly string[]): string {
  if (!existing.includes(base)) return base;
  let counter = 2;
  while (existing.includes(`${base} (${counter})`)) counter++;
  return `${base} (${counter})`;
}

export default ServiceWizard;
