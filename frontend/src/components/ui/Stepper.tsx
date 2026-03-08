import { type ReactNode } from 'react';

export interface StepDefinition {
  id: string;
  label: string;
  description?: string;
  optional?: boolean;
}

export type StepStatus =
  | 'pending'
  | 'active'
  | 'completed'
  | 'error'
  | 'skipped';

interface StepperHeaderProps {
  steps: StepDefinition[];
  currentStep: number;
  stepStatuses?: Record<string, StepStatus>;
  onStepClick?: (stepIndex: number) => void;
}

function StepperHeader({
  steps,
  currentStep,
  stepStatuses = {},
  onStepClick,
}: StepperHeaderProps) {
  const getStatus = (index: number): StepStatus => {
    const step = steps[index];
    if (stepStatuses[step.id]) return stepStatuses[step.id];
    if (index < currentStep) return 'completed';
    if (index === currentStep) return 'active';
    return 'pending';
  };

  const statusColors: Record<StepStatus, string> = {
    pending: 'bg-gray-300 text-gray-600',
    active: 'bg-blue-600 text-white',
    completed: 'bg-green-500 text-white',
    error: 'bg-red-500 text-white',
    skipped: 'bg-gray-200 text-gray-400',
  };

  const lineColors: Record<StepStatus, string> = {
    pending: 'bg-gray-300',
    active: 'bg-gray-300',
    completed: 'bg-green-500',
    error: 'bg-red-500',
    skipped: 'bg-gray-200',
  };

  return (
    <div className="flex items-center justify-between mb-6 px-2 flex-shrink-0">
      {steps.map((step, index) => {
        const s = getStatus(index);
        const clickable =
          onStepClick && s === 'completed' && index < currentStep;

        return (
          <div key={step.id} className="flex items-center flex-1 last:flex-none">
            <div className="flex flex-col items-center">
              <button
                type="button"
                disabled={!clickable}
                onClick={() => clickable && onStepClick(index)}
                className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium transition-colors ${statusColors[s]} ${
                  clickable
                    ? 'cursor-pointer hover:ring-2 hover:ring-blue-300'
                    : 'cursor-default'
                }`}
              >
                {s === 'completed' ? '✓' : index + 1}
              </button>
              <span
                className={`mt-1 text-xs text-center max-w-[80px] leading-tight ${
                  s === 'active'
                    ? 'text-blue-600 font-medium'
                    : 'text-gray-500'
                }`}
              >
                {step.label}
              </span>
            </div>
            {index < steps.length - 1 && (
              <div
                className={`flex-1 h-0.5 mx-2 mt-[-16px] ${lineColors[getStatus(index)]}`}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}

interface StepperNavigationProps {
  currentStep: number;
  totalSteps: number;
  onNext: () => void;
  onBack: () => void;
  onCancel: () => void;
  nextLabel?: string;
  backLabel?: string;
  cancelLabel?: string;
  nextDisabled?: boolean;
  isSubmitting?: boolean;
  showBack?: boolean;
  showNext?: boolean;
}

function StepperNavigation({
  currentStep,
  totalSteps,
  onNext,
  onBack,
  onCancel,
  nextLabel,
  backLabel = 'Back',
  cancelLabel = 'Cancel',
  nextDisabled = false,
  isSubmitting = false,
  showBack = true,
  showNext = true,
}: StepperNavigationProps) {
  const isFinalStep = currentStep === totalSteps - 1;
  const defaultNextLabel = isFinalStep ? 'Confirm Import' : 'Next';
  const label = nextLabel || defaultNextLabel;

  return (
    <div className="flex items-center justify-between pt-4 border-t border-gray-200 mt-4 flex-shrink-0">
      <button
        type="button"
        onClick={onCancel}
        disabled={isSubmitting}
        className="px-4 py-2 text-sm text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50"
      >
        {cancelLabel}
      </button>
      <div className="flex items-center space-x-3">
        {showBack && currentStep > 0 && (
          <button
            type="button"
            onClick={onBack}
            disabled={isSubmitting}
            className="px-4 py-2 text-sm text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50"
          >
            {backLabel}
          </button>
        )}
        {showNext && (
          <button
            type="button"
            onClick={onNext}
            disabled={nextDisabled || isSubmitting}
            className={`px-4 py-2 text-sm text-white rounded-lg disabled:opacity-50 ${
              isFinalStep
                ? 'bg-green-600 hover:bg-green-700'
                : 'bg-blue-600 hover:bg-blue-700'
            }`}
          >
            {isSubmitting ? 'Importing...' : label}
          </button>
        )}
      </div>
    </div>
  );
}

interface StepperContainerProps {
  steps: StepDefinition[];
  currentStep: number;
  children: ReactNode;
  onNext: () => void;
  onBack: () => void;
  onCancel: () => void;
  onStepClick?: (stepIndex: number) => void;
  stepStatuses?: Record<string, StepStatus>;
  nextLabel?: string;
  cancelLabel?: string;
  nextDisabled?: boolean;
  isSubmitting?: boolean;
  showBack?: boolean;
  showNext?: boolean;
}

function StepperContainer({
  steps,
  currentStep,
  children,
  onNext,
  onBack,
  onCancel,
  onStepClick,
  stepStatuses,
  nextLabel,
  cancelLabel,
  nextDisabled,
  isSubmitting,
  showBack = true,
  showNext = true,
}: StepperContainerProps) {
  return (
    <div className="flex flex-col flex-1 min-h-0">
      <StepperHeader
        steps={steps}
        currentStep={currentStep}
        stepStatuses={stepStatuses}
        onStepClick={onStepClick}
      />
      <div className="flex-1 overflow-y-auto min-h-0">{children}</div>
      <StepperNavigation
        currentStep={currentStep}
        totalSteps={steps.length}
        onNext={onNext}
        onBack={onBack}
        onCancel={onCancel}
        nextLabel={nextLabel}
        cancelLabel={cancelLabel}
        nextDisabled={nextDisabled}
        isSubmitting={isSubmitting}
        showBack={showBack}
        showNext={showNext}
      />
    </div>
  );
}

export { StepperHeader, StepperNavigation, StepperContainer };
export type { StepperHeaderProps, StepperNavigationProps, StepperContainerProps };
