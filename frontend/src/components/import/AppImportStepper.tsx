import { useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { StepperContainer } from '../ui/Stepper';
import type { StepDefinition, StepStatus } from '../ui/Stepper';
import type {
  AppImportPreview,
  ConflictMode,
  FullAppImportResponse,
} from '../../types/import';
import { apiService } from '../../services/api';
import AppStepUpload from './steps/AppStepUpload';
import AppStepConfig from './steps/AppStepConfig';
import AppStepSelect from './steps/AppStepSelect';
import AppStepApiKeys from './steps/AppStepApiKeys';
import AppStepConflicts from './steps/AppStepConflicts';
import AppStepReview from './steps/AppStepReview';
import AppStepResult from './steps/AppStepResult';

const STEPS: StepDefinition[] = [
  { id: 'upload', label: 'Upload' },
  { id: 'config', label: 'App Config' },
  { id: 'select', label: 'Components' },
  { id: 'apikeys', label: 'API Keys', optional: true },
  { id: 'conflicts', label: 'Conflicts', optional: true },
  { id: 'review', label: 'Review' },
  { id: 'result', label: 'Result' },
];

interface Props {
  isOpen: boolean;
  onClose: () => void;
  onImportComplete: () => void;
}

function makeKey(type: string, name: string): string {
  return `${type}:${name}`;
}

function AppImportStepper({
  isOpen,
  onClose,
  onImportComplete,
}: Readonly<Props>) {
  const navigate = useNavigate();

  // Step state
  const [currentStep, setCurrentStep] = useState(0);
  const [stepStatuses, setStepStatuses] = useState<
    Record<string, StepStatus>
  >({});

  // Step 1: Upload
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] =
    useState<AppImportPreview | null>(null);
  const [isValidating, setIsValidating] = useState(false);
  const [validationError, setValidationError] = useState<
    string | null
  >(null);

  // Step 2: App Config
  const [appName, setAppName] = useState('');
  const [hasAppConflict, setHasAppConflict] = useState(false);
  const [appConflictMode, setAppConflictMode] =
    useState<ConflictMode>('rename');

  // Step 3: Component Selection
  const [selection, setSelection] = useState<
    Record<string, boolean>
  >({});

  // Step 4: API Keys
  const [apiKeys, setApiKeys] = useState<
    Record<string, string>
  >({});

  // Step 5: Component Conflicts
  const [componentConflictMode, setComponentConflictMode] =
    useState<ConflictMode>('rename');

  // Step 7: Result
  const [importResult, setImportResult] =
    useState<FullAppImportResponse | null>(null);
  const [isImporting, setIsImporting] = useState(false);
  const [importError, setImportError] = useState<
    string | null
  >(null);

  const handleFileSelect = useCallback(
    async (selectedFile: File) => {
      setFile(selectedFile);
      setPreview(null);
      setValidationError(null);
      setIsValidating(true);

      try {
        const result: AppImportPreview =
          await apiService.previewAppImport(selectedFile);
        setPreview(result);
        setAppName(result.app_name);

        // Check app name conflict from warnings
        setHasAppConflict(
          result.global_warnings.some((w) =>
            w.includes('already exists')
          )
        );

        // Initialize selection: all selected by default
        const sel: Record<string, boolean> = {};
        const allItems = [
          ...result.ai_services.map((c) => ({
            type: 'ai_service',
            name: c.component_name,
          })),
          ...result.embedding_services.map((c) => ({
            type: 'embedding_service',
            name: c.component_name,
          })),
          ...result.output_parsers.map((c) => ({
            type: 'output_parser',
            name: c.component_name,
          })),
          ...result.mcp_configs.map((c) => ({
            type: 'mcp_config',
            name: c.component_name,
          })),
          ...result.silos.map((c) => ({
            type: 'silo',
            name: c.component_name,
          })),
          ...result.repositories.map((c) => ({
            type: 'repository',
            name: c.component_name,
          })),
          ...result.domains.map((c) => ({
            type: 'domain',
            name: c.component_name,
          })),
          ...result.agents.map((c) => ({
            type: 'agent',
            name: c.component_name,
          })),
        ];
        for (const item of allItems) {
          sel[makeKey(item.type, item.name)] = true;
        }
        setSelection(sel);
      } catch (err: unknown) {
        setValidationError(
          err instanceof Error ? err.message : 'Failed to validate export file'
        );
      } finally {
        setIsValidating(false);
      }
    },
    []
  );

  const hasServicesNeedingKeys = (): boolean => {
    if (!preview) return false;
    return [...preview.ai_services, ...preview.embedding_services].some(
      (svc) => {
        const key = `${svc.component_type}:${svc.component_name}`;
        return selection[key] && svc.needs_api_key;
      }
    );
  };

  const isNextDisabled = (): boolean => {
    switch (currentStep) {
      case 0: // Upload
        return !preview || isValidating;
      case 1: // Config
        return !appName.trim();
      case 2: // Select
        return (
          Object.values(selection).filter(Boolean)
            .length === 0
        );
      case 3: // API Keys - always can proceed
        return false;
      case 4: // Conflicts - always can proceed
        return false;
      case 5: // Review (confirm)
        return false;
      default:
        return false;
    }
  };

  const handleNext = async () => {
    // Step 3 -> Step 4 (API Keys): skip if no services need keys
    if (currentStep === 3 && !hasServicesNeedingKeys()) {
      setStepStatuses((prev) => ({
        ...prev,
        apikeys: 'skipped',
      }));
      setCurrentStep(4);
      return;
    }

    // Step 4 -> Step 5 (Conflicts): auto-skip since new app
    if (currentStep === 4) {
      setStepStatuses((prev) => ({
        ...prev,
        conflicts: 'skipped',
      }));
      setCurrentStep(5);
      return;
    }

    // Step 5 (Review): execute import
    if (currentStep === 5) {
      await executeImport();
      return;
    }

    setCurrentStep((prev) => prev + 1);
  };

  const handleBack = () => {
    let targetStep = currentStep - 1;

    // Skip back over auto-skipped steps
    if (
      targetStep === 4 &&
      stepStatuses.conflicts === 'skipped'
    ) {
      targetStep = 3;
    }
    if (
      targetStep === 3 &&
      stepStatuses.apikeys === 'skipped'
    ) {
      targetStep = 2;
    }

    setCurrentStep(Math.max(0, targetStep));
  };

  const executeImport = async () => {
    if (!file) return;

    setCurrentStep(6);
    setIsImporting(true);
    setImportError(null);
    setImportResult(null);

    try {
      // Build component selection map: type -> list of selected names
      const componentSelection: Record<string, string[]> =
        {};
      for (const [key, selected] of Object.entries(
        selection
      )) {
        if (!selected) continue;
        const [type, ...nameParts] = key.split(':');
        const name = nameParts.join(':');
        if (!componentSelection[type]) {
          componentSelection[type] = [];
        }
        componentSelection[type].push(name);
      }

      const result = await apiService.importAppWithOptions(
        file,
        {
          conflictMode: hasAppConflict
            ? appConflictMode
            : componentConflictMode,
          newAppName:
            hasAppConflict &&
            appConflictMode === 'rename'
              ? appName
              : undefined,
          componentSelection,
          apiKeys,
        }
      );

      setImportResult(result);
      if (result.success) {
        setStepStatuses((prev) => ({
          ...prev,
          result: 'completed',
        }));
        onImportComplete();
      } else {
        setStepStatuses((prev) => ({
          ...prev,
          result: 'error',
        }));
      }
    } catch (err: unknown) {
      setImportError(
        err instanceof Error ? err.message : 'Import failed unexpectedly'
      );
      setStepStatuses((prev) => ({
        ...prev,
        result: 'error',
      }));
    } finally {
      setIsImporting(false);
    }
  };

  const handleRetry = () => {
    setImportResult(null);
    setImportError(null);
    setStepStatuses((prev) => {
      const next = { ...prev };
      delete next.result;
      return next;
    });
    setCurrentStep(5); // Go back to review
  };

  const handleOpenApp = () => {
    if (importResult?.summary?.app_id) {
      navigate(`/apps/${importResult.summary.app_id}`);
    }
    onClose();
  };

  const handleStepClick = (stepIndex: number) => {
    if (stepIndex < currentStep && currentStep < 6) {
      setCurrentStep(stepIndex);
    }
  };

  const handleApiKeyChange = (
    serviceName: string,
    key: string
  ) => {
    setApiKeys((prev) => ({
      ...prev,
      [serviceName]: key,
    }));
  };

  if (!isOpen) return null;

  const isFinalStep = currentStep === 6;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg w-full max-w-3xl mx-4 max-h-[85vh] flex flex-col">
        {/* Header */}
        <div className="px-6 pt-6 pb-2 border-b border-gray-200">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-gray-900">
              Import App
            </h2>
            <button
              type="button"
              onClick={onClose}
              aria-label="Close"
              className="text-gray-400 hover:text-gray-600 text-xl leading-none"
            >
              &times;
            </button>
          </div>
        </div>

        {/* Body with Stepper */}
        <div className="flex-1 min-h-0 flex flex-col px-6 py-4">
          <StepperContainer
            steps={STEPS}
            currentStep={currentStep}
            stepStatuses={stepStatuses}
            onStepClick={handleStepClick}
            onNext={handleNext}
            onBack={handleBack}
            onCancel={onClose}
            nextDisabled={isNextDisabled()}
            isSubmitting={isImporting}
            showBack={!isFinalStep}
            showNext={!isFinalStep}
            nextLabel={
              currentStep === 5
                ? 'Confirm Import'
                : undefined
            }
            cancelLabel={
              isFinalStep ? 'Close' : 'Cancel'
            }
          >
            {currentStep === 0 && (
              <AppStepUpload
                file={file}
                onFileSelect={handleFileSelect}
                preview={preview}
                isValidating={isValidating}
                validationError={validationError}
              />
            )}
            {currentStep === 1 && preview && (
              <AppStepConfig
                appName={appName}
                onAppNameChange={setAppName}
                hasConflict={hasAppConflict}
                conflictMode={appConflictMode}
                onConflictModeChange={setAppConflictMode}
              />
            )}
            {currentStep === 2 && preview && (
              <AppStepSelect
                preview={preview}
                selection={selection}
                onSelectionChange={setSelection}
              />
            )}
            {currentStep === 3 && preview && (
              <AppStepApiKeys
                preview={preview}
                selection={selection}
                apiKeys={apiKeys}
                onApiKeyChange={handleApiKeyChange}
              />
            )}
            {currentStep === 4 && (
              <AppStepConflicts
                hasConflicts={false}
                conflictMode={componentConflictMode}
                onConflictModeChange={
                  setComponentConflictMode
                }
              />
            )}
            {currentStep === 5 && preview && (
              <AppStepReview
                preview={preview}
                appName={appName}
                conflictMode={
                  hasAppConflict
                    ? appConflictMode
                    : componentConflictMode
                }
                selection={selection}
                apiKeys={apiKeys}
              />
            )}
            {currentStep === 6 && (
              <AppStepResult
                result={importResult}
                isImporting={isImporting}
                importError={importError}
                onClose={onClose}
                onOpenApp={handleOpenApp}
                onRetry={handleRetry}
              />
            )}
          </StepperContainer>
        </div>
      </div>
    </div>
  );
}

export default AppImportStepper;
