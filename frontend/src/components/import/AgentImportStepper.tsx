import { useState, useEffect, useCallback } from 'react';
import { StepperContainer } from '../ui/Stepper';
import type { StepDefinition, StepStatus } from '../ui/Stepper';
import type {
  AgentImportPreview,
  ConflictMode,
  ImportResponse,
} from '../../types/import';
import { apiService } from '../../services/api';
import AgentStepUpload from './steps/AgentStepUpload';
import AgentStepDeps from './steps/AgentStepDeps';
import AgentStepConflicts from './steps/AgentStepConflicts';
import AgentStepReview from './steps/AgentStepReview';
import AgentStepResult from './steps/AgentStepResult';

const STEPS: StepDefinition[] = [
  { id: 'upload', label: 'Upload' },
  { id: 'deps', label: 'Dependencies' },
  { id: 'conflicts', label: 'Conflicts', optional: true },
  { id: 'review', label: 'Review' },
  { id: 'result', label: 'Result' },
];

interface Props {
  appId: number;
  isOpen: boolean;
  onClose: () => void;
  onImportComplete: () => void;
}

function AgentImportStepper({
  appId,
  isOpen,
  onClose,
  onImportComplete,
}: Readonly<Props>) {
  // Step state
  const [currentStep, setCurrentStep] = useState(0);
  const [stepStatuses, setStepStatuses] = useState<
    Record<string, StepStatus>
  >({});

  // Step 1: Upload
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] =
    useState<AgentImportPreview | null>(null);
  const [isValidating, setIsValidating] = useState(false);
  const [validationError, setValidationError] = useState<
    string | null
  >(null);

  // Step 2: Dependencies
  const [useExistingAIService, setUseExistingAIService] =
    useState(false);
  const [selectedAIServiceId, setSelectedAIServiceId] =
    useState<number | null>(null);
  const [availableAIServices, setAvailableAIServices] = useState<
    Array<{ id: number; name: string }>
  >([]);
  const [importBundledSilo, setImportBundledSilo] = useState(true);
  const [importBundledOutputParser, setImportBundledOutputParser] =
    useState(true);
  const [importBundledMCPConfigs, setImportBundledMCPConfigs] =
    useState(true);
  const [importBundledAgentTools, setImportBundledAgentTools] =
    useState(true);

  // Step 3: Conflicts
  const [conflictMode, setConflictMode] =
    useState<ConflictMode>('fail');
  const [newName, setNewName] = useState('');

  // Step 5: Result
  const [importResult, setImportResult] =
    useState<ImportResponse | null>(null);
  const [isImporting, setIsImporting] = useState(false);
  const [importError, setImportError] = useState<string | null>(
    null
  );

  // Load available AI services on open
  useEffect(() => {
    if (!isOpen) return;

    const loadAIServices = async () => {
      try {
        const services = await apiService.getAIServices(appId);
        setAvailableAIServices(
          (services as Array<{ service_id: number; name: string }>).map(
            (svc) => ({ id: svc.service_id, name: svc.name })
          )
        );
      } catch {
        // Non-critical - user can still import bundled
      }
    };

    loadAIServices();
  }, [isOpen, appId]);

  const handleFileSelect = useCallback(
    async (selectedFile: File) => {
      setFile(selectedFile);
      setPreview(null);
      setValidationError(null);
      setIsValidating(true);

      try {
        const result = await apiService.previewAgentImport(
          appId,
          selectedFile
        );
        setPreview(result);

        // Pre-fill conflict name if there's a conflict
        if (result.agent.has_conflict) {
          setNewName(
            `${result.agent.component_name} (imported)`
          );
        }

        // If no bundled AI service, force "use existing"
        if (!result.ai_service) {
          setUseExistingAIService(true);
        }
      } catch (err: unknown) {
        setValidationError(
          err instanceof Error ? err.message : 'Failed to validate export file'
        );
      } finally {
        setIsValidating(false);
      }
    },
    [appId]
  );

  const isNextDisabled = (): boolean => {
    switch (currentStep) {
      case 0: // Upload
        return !preview || isValidating;
      case 1: // Dependencies
        if (useExistingAIService && !selectedAIServiceId) {
          return true;
        }
        if (
          !preview?.ai_service &&
          !selectedAIServiceId
        ) {
          return true;
        }
        return false;
      case 2: // Conflicts
        if (
          conflictMode === 'rename' &&
          !newName.trim()
        ) {
          return true;
        }
        return false;
      case 3: // Review (confirm button)
        return false;
      default:
        return false;
    }
  };

  const handleNext = async () => {
    if (currentStep === 2 && !preview?.agent.has_conflict) {
      // Auto-skip conflicts step
      setStepStatuses((prev) => ({
        ...prev,
        conflicts: 'skipped',
      }));
      setCurrentStep(3);
      return;
    }

    if (currentStep === 3) {
      // Confirm Import -> execute
      await executeImport();
      return;
    }

    setCurrentStep((prev) => prev + 1);
  };

  const handleBack = () => {
    if (currentStep === 3 && !preview?.agent.has_conflict) {
      // Skip back over auto-skipped conflicts step
      setCurrentStep(1);
      return;
    }
    setCurrentStep((prev) => Math.max(0, prev - 1));
  };

  const executeImport = async () => {
    if (!file) return;

    setCurrentStep(4);
    setIsImporting(true);
    setImportError(null);
    setImportResult(null);

    try {
      const result = await apiService.importAgentWithOptions(
        appId,
        file,
        {
          conflictMode,
          newName:
            conflictMode === 'rename' ? newName : undefined,
          selectedAIServiceId:
            useExistingAIService
              ? selectedAIServiceId ?? undefined
              : undefined,
          importBundledSilo,
          importBundledOutputParser,
          importBundledMCPConfigs,
          importBundledAgentTools,
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
    setCurrentStep(3); // Go back to review step
  };

  const handleViewAgent = () => {
    onClose();
  };

  const handleStepClick = (stepIndex: number) => {
    if (stepIndex < currentStep && currentStep < 4) {
      setCurrentStep(stepIndex);
    }
  };

  if (!isOpen) return null;

  const isFinalStep = currentStep === 4;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg w-full max-w-2xl mx-4 max-h-[85vh] flex flex-col">
        {/* Header */}
        <div className="px-6 pt-6 pb-2 border-b border-gray-200">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-gray-900">
              Import Agent
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
              currentStep === 3
                ? 'Confirm Import'
                : undefined
            }
            cancelLabel={isFinalStep ? 'Close' : 'Cancel'}
          >
            {currentStep === 0 && (
              <AgentStepUpload
                file={file}
                onFileSelect={handleFileSelect}
                preview={preview}
                isValidating={isValidating}
                validationError={validationError}
              />
            )}
            {currentStep === 1 && preview && (
              <AgentStepDeps
                preview={preview}
                useExistingAIService={useExistingAIService}
                onUseExistingAIServiceChange={
                  setUseExistingAIService
                }
                selectedAIServiceId={selectedAIServiceId}
                onSelectedAIServiceIdChange={
                  setSelectedAIServiceId
                }
                availableAIServices={availableAIServices}
                importBundledSilo={importBundledSilo}
                onImportBundledSiloChange={
                  setImportBundledSilo
                }
                importBundledOutputParser={
                  importBundledOutputParser
                }
                onImportBundledOutputParserChange={
                  setImportBundledOutputParser
                }
                importBundledMCPConfigs={
                  importBundledMCPConfigs
                }
                onImportBundledMCPConfigsChange={
                  setImportBundledMCPConfigs
                }
                importBundledAgentTools={
                  importBundledAgentTools
                }
                onImportBundledAgentToolsChange={
                  setImportBundledAgentTools
                }
              />
            )}
            {currentStep === 2 && preview && (
              <AgentStepConflicts
                preview={preview}
                conflictMode={conflictMode}
                onConflictModeChange={setConflictMode}
                newName={newName}
                onNewNameChange={setNewName}
              />
            )}
            {currentStep === 3 && preview && (
              <AgentStepReview
                preview={preview}
                conflictMode={conflictMode}
                newName={newName}
                useExistingAIService={useExistingAIService}
                selectedAIServiceId={selectedAIServiceId}
                availableAIServices={availableAIServices}
                importBundledSilo={importBundledSilo}
                importBundledOutputParser={
                  importBundledOutputParser
                }
                importBundledMCPConfigs={
                  importBundledMCPConfigs
                }
                importBundledAgentTools={
                  importBundledAgentTools
                }
              />
            )}
            {currentStep === 4 && (
              <AgentStepResult
                result={importResult}
                isImporting={isImporting}
                importError={importError}
                onClose={onClose}
                onViewAgent={handleViewAgent}
                onRetry={handleRetry}
              />
            )}
          </StepperContainer>
        </div>
      </div>
    </div>
  );
}

export default AgentImportStepper;
