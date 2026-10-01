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
  ExistingSandboxService,
  ExistingService,
  ProviderModelInfo,
  SandboxServiceFormData,
  ServiceFormData,
  ServiceKind,
  ServiceScope,
  ServiceWizardMode,
} from '../../../types/services';

const STEPS_WITH_MODEL: StepDefinition[] = [
  { id: 'provider', label: 'Provider' },
  { id: 'credentials', label: 'Credentials' },
  { id: 'model', label: 'Model' },
  { id: 'confirm', label: 'Confirm' },
];

/** Sandbox services have no model to pick — the Model step is skipped entirely. */
const STEPS_WITHOUT_MODEL: StepDefinition[] = [
  { id: 'provider', label: 'Provider' },
  { id: 'credentials', label: 'Credentials' },
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
  readonly initialService?: ExistingService | ExistingSandboxService | null;
  /** Existing service names in scope, used to disambiguate auto-generated names. */
  readonly existingNames?: readonly string[];
  readonly onClose: () => void;
  /**
   * Declared with method shorthand (not an arrow-typed property) on purpose:
   * TypeScript checks method-shorthand parameters bivariantly, so callers
   * that only ever deal with one kind (e.g. a page fixed to `kind="ai"`) can
   * keep a narrower `(data: ServiceFormData) => Promise<void>` handler
   * without widening it to the full union.
   */
  onSave(data: ServiceFormData | SandboxServiceFormData): Promise<void>;
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
      if (kind === 'sandbox') {
        const svc = initialService as ExistingSandboxService;
        setCredentials({
          ...EMPTY_CREDENTIALS,
          // We never receive the real key — leave it blank so the user
          // re-enters it (required to test the connection again).
          api_key: '',
          base_url: svc.base_url || '',
          image: svc.opensandbox_image || '',
          target: svc.daytona_target || '',
          template: svc.e2b_template || '',
        });
      } else {
        const svc = initialService as ExistingService;
        setCredentials({
          ...EMPTY_CREDENTIALS,
          // We never receive the real key — leave it blank so the user
          // re-enters it (required to list models again).
          api_key: '',
          base_url: svc.base_url || '',
          api_version: svc.api_version || '',
          aws_access_key_id: svc.aws_access_key_id || '',
          aws_region: svc.aws_region || '',
        });
        setManualModelName(svc.model_name || '');
        setSupportsVideo(!!svc.supports_video);
      }
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

  // Sandbox services have no "model" concept — the Model step is skipped
  // entirely (see `steps` below), so a model name never drives the name.
  const steps = kind === 'sandbox' ? STEPS_WITHOUT_MODEL : STEPS_WITH_MODEL;

  const autoName = useMemo(() => {
    if (!provider) return '';
    if (kind === 'sandbox') {
      return ensureUnique(descriptor?.label || provider, existingNames);
    }
    const modelPart = descriptor?.supportsModelListing
      ? selectedModel?.display_name || selectedModel?.id || ''
      : manualModelName;
    if (!modelPart) return '';
    const base = `${descriptor?.label || provider} - ${modelPart}`;
    return ensureUnique(base, existingNames);
  }, [provider, kind, descriptor, selectedModel, manualModelName, existingNames]);

  const stepDisabled = useMemo(() => {
    switch (steps[currentStep].id) {
      case 'provider':
        return !provider;
      case 'credentials':
        return isCredentialsStepDisabled(descriptor, credentials);
      case 'model':
        if (!descriptor?.supportsModelListing) return !manualModelName.trim();
        return !selectedModel;
      case 'confirm':
        return !autoName;
      default:
        return false;
    }
  }, [steps, currentStep, provider, descriptor, credentials, selectedModel, manualModelName, autoName]);

  const handleNext = async () => {
    const stepId = steps[currentStep].id;
    if (stepId === 'confirm') {
      await handleSubmit();
      return;
    }
    // Any edit upstream of the confirm step invalidates a previous
    // test result — credentials or the selected model may have changed.
    setTestResult(null);
    setStepStatuses((prev) => ({ ...prev, [stepId]: 'completed' }));
    setCurrentStep((s) => Math.min(s + 1, steps.length - 1));
  };

  const handleBack = () => {
    setStepStatuses((prev) => {
      const next = { ...prev };
      const stepId = steps[currentStep].id;
      delete next[stepId];
      return next;
    });
    setCurrentStep((s) => Math.max(s - 1, 0));
  };

  const buildPayload = (): ServiceFormData | SandboxServiceFormData => {
    if (kind === 'sandbox') {
      const sandboxPayload: SandboxServiceFormData = {
        name: autoName || provider,
        provider,
        api_key: credentials.api_key,
        base_url: credentials.base_url,
        opensandbox_image: credentials.image?.trim() || undefined,
        daytona_target: credentials.target?.trim() || undefined,
        e2b_template: credentials.template?.trim() || undefined,
      };
      return sandboxPayload;
    }
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
      aws_access_key_id: credentials.aws_access_key_id?.trim() || undefined,
      aws_region: credentials.aws_region?.trim() || undefined,
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
      // In edit-model mode the existing service is being mutated, so we
      // pass its id to the backend — that allows the masked API key to be
      // resolved from DB instead of forcing the user to re-type the secret.
      const editServiceId = mode === 'edit-model' ? initialService?.service_id : undefined;
      setTestResult(await client.testConnection(buildPayload(), editServiceId));
    } catch (e) {
      setTestResult({
        status: 'error',
        message: e instanceof Error ? e.message : 'Test failed',
      });
    } finally {
      setTesting(false);
    }
  };

  let title = 'Add Sandbox Service';
  if (kind === 'ai') title = 'Add AI Service';
  else if (kind === 'embedding') title = 'Add Embedding Service';
  if (mode === 'edit-model') title = kind === 'sandbox' ? 'Edit sandbox service' : 'Change model';

  return (
    <Modal isOpen={isOpen} onClose={onClose} title={title} size="xlarge">
      <div className="flex flex-col" style={{ minHeight: '500px' }}>
        <StepperContainer
          steps={steps}
          currentStep={currentStep}
          stepStatuses={stepStatuses}
          onNext={handleNext}
          onBack={handleBack}
          onCancel={onClose}
          nextDisabled={stepDisabled}
          isSubmitting={submitting}
          nextLabel={steps[currentStep].id === 'confirm' ? (submitting ? 'Saving...' : 'Save') : undefined}
          showBack={mode === 'create' || currentStep > 1}
        >
          <div className="px-2 py-3">
            {steps[currentStep].id === 'provider' && (
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
            {steps[currentStep].id === 'credentials' && (
              <CredentialsStep
                kind={kind}
                provider={provider}
                mode={mode}
                value={credentials}
                onChange={setCredentials}
              />
            )}
            {steps[currentStep].id === 'model' && (
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
            {steps[currentStep].id === 'confirm' && (
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

/** Whether the credentials step is incomplete for the chosen provider. */
function isCredentialsStepDisabled(
  descriptor: ReturnType<typeof getProviderDescriptor>,
  credentials: CredentialsState,
): boolean {
  if (!descriptor) return true;
  if (descriptor.apiKey === 'required' && !credentials.api_key.trim()) return true;
  if (descriptor.needsBaseUrl && !credentials.base_url.trim()) return true;
  const manualFields = descriptor.manualFields ?? [];
  if (manualFields.includes('aws_access_key_id') && !credentials.aws_access_key_id?.trim()) {
    return true;
  }
  if (manualFields.includes('aws_region') && !credentials.aws_region?.trim()) {
    return true;
  }
  return false;
}

export default ServiceWizard;
