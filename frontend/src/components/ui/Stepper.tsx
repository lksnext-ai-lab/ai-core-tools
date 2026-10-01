import { type ReactNode } from 'react';
import { Check } from 'lucide-react';

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
}: Readonly<StepperHeaderProps>) {
  const getStatus = (index: number): StepStatus => {
    const step = steps[index];
    if (stepStatuses[step.id]) return stepStatuses[step.id];
    if (index < currentStep) return 'completed';
    if (index === currentStep) return 'active';
    return 'pending';
  };

  const statusColors: Record<StepStatus, string> = {
    pending: 'bg-surface border border-line-strong text-fg-tertiary dark:bg-surface-dark dark:border-line-strong-dark dark:text-fg-tertiary-dark',
    active: 'bg-ink text-ink-on ring-2 ring-accent ring-offset-2 dark:bg-ink-dark dark:text-ink-on-dark dark:ring-accent-dark dark:ring-offset-surface-dark',
    completed: 'bg-success-bg text-success border border-success-border dark:bg-success-bg-dark dark:text-success-dark dark:border-success-border-dark',
    error: 'bg-error-bg text-error border border-error-border dark:bg-error-bg-dark dark:text-error-dark dark:border-error-border-dark',
    skipped: 'bg-surface-hover text-fg-faint dark:bg-surface-hover-dark dark:text-fg-faint-dark',
  };

  const lineColors: Record<StepStatus, string> = {
    pending: 'bg-line dark:bg-line-dark',
    active: 'bg-line dark:bg-line-dark',
    completed: 'bg-success dark:bg-success-dark',
    error: 'bg-error dark:bg-error-dark',
    skipped: 'bg-line dark:bg-line-dark',
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
                    ? 'cursor-pointer hover:ring-2 hover:ring-line-strong dark:hover:ring-line-strong-dark'
                    : 'cursor-default'
                }`}
              >
                {s === 'completed' ? <Check className="w-4 h-4" /> : index + 1}
              </button>
              <span
                className={`mt-1 text-xs text-center max-w-[80px] leading-tight ${
                  s === 'active'
                    ? 'text-fg font-medium dark:text-fg-dark'
                    : 'text-fg-tertiary dark:text-fg-tertiary-dark'
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
}: Readonly<StepperNavigationProps>) {
  const isFinalStep = currentStep === totalSteps - 1;
  const defaultNextLabel = isFinalStep ? 'Confirm Import' : 'Next';
  const label = nextLabel || defaultNextLabel;

  return (
    <div className="flex items-center justify-between pt-4 border-t border-line dark:border-line-dark mt-4 flex-shrink-0">
      <button
        type="button"
        onClick={onCancel}
        disabled={isSubmitting}
        className="px-4 py-2 text-sm font-medium text-fg bg-transparent border border-line-strong rounded-lg hover:bg-surface-hover dark:text-fg-dark dark:border-line-strong-dark dark:hover:bg-surface-hover-dark disabled:opacity-50"
      >
        {cancelLabel}
      </button>
      <div className="flex items-center space-x-3">
        {showBack && currentStep > 0 && (
          <button
            type="button"
            onClick={onBack}
            disabled={isSubmitting}
            className="px-4 py-2 text-sm font-medium text-fg bg-transparent border border-line-strong rounded-lg hover:bg-surface-hover dark:text-fg-dark dark:border-line-strong-dark dark:hover:bg-surface-hover-dark disabled:opacity-50"
          >
            {backLabel}
          </button>
        )}
        {showNext && (
          <button
            type="button"
            onClick={onNext}
            disabled={nextDisabled || isSubmitting}
            className={`px-4 py-2 text-sm font-medium text-ink-on rounded-lg disabled:opacity-50 dark:text-ink-on-dark ${
              isFinalStep
                ? 'font-semibold bg-ink hover:bg-ink/85 dark:bg-ink-dark dark:hover:bg-ink-dark/85'
                : 'bg-ink hover:bg-ink/85 dark:bg-ink-dark dark:hover:bg-ink-dark/85'
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
}: Readonly<StepperContainerProps>) {
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
