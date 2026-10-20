import { ButtonApp } from './ButtonApp';

interface FormActionsProps {
  onCancel: () => void;
  isSubmitting: boolean;
  /** Picks the default submit label ("Update" / "Create") when no submitLabel is given. */
  isEditing?: boolean;
  submitLabel?: string;
  submittingLabel?: string;
  cancelLabel?: string;
  submitClassName?: string;
  cancelClassName?: string;
  containerClassName?: string;
  showCancel?: boolean;
  submitDisabled?: boolean; // Additional condition to disable submit button
}

function getDefaultSubmitLabel(isEditing: boolean | undefined): string {
  if (isEditing === undefined) return 'Save';
  return isEditing ? 'Update' : 'Create';
}

/**
 * Reusable form action buttons (Cancel/Submit) built on ButtonApp.
 * Provides consistent button styling and behavior across all forms.
 */
export function FormActions({
  onCancel,
  isSubmitting,
  isEditing,
  submitLabel,
  submittingLabel = 'Saving...',
  cancelLabel = 'Cancel',
  submitClassName = '',
  cancelClassName = '',
  containerClassName = '',
  showCancel = true,
  submitDisabled = false,
}: Readonly<FormActionsProps>) {
  const finalSubmitLabel = submitLabel || getDefaultSubmitLabel(isEditing);

  return (
    <div className={`flex items-center justify-end gap-3 pt-4 border-t border-line dark:border-line-dark ${containerClassName}`}>
      {showCancel && (
        <ButtonApp
          label={cancelLabel}
          type="button"
          onClick={onCancel}
          disabled={isSubmitting}
          variant="secondary"
          size="medium"
          className={cancelClassName}
        />
      )}
      <ButtonApp
        label={isSubmitting ? submittingLabel : finalSubmitLabel}
        type="submit"
        disabled={submitDisabled}
        loading={isSubmitting}
        variant="primary"
        size="medium"
        className={submitClassName}
      />
    </div>
  );
}

export default FormActions;
