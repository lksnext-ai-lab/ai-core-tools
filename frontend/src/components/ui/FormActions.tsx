import { ButtonApp } from './ButtonApp';
import { useTranslation } from 'react-i18next';

interface FormActionsProps {
  onCancel: () => void;
  isSubmitting: boolean;
  /** Picks a translated default submit label when no submitLabel is given. */
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

/**
 * Reusable form action buttons (Cancel/Submit) built on ButtonApp.
 * Provides consistent button styling and behavior across all forms.
 */
export function FormActions({
  onCancel,
  isSubmitting,
  isEditing,
  submitLabel,
  submittingLabel,
  cancelLabel,
  submitClassName = '',
  cancelClassName = '',
  containerClassName = '',
  showCancel = true,
  submitDisabled = false,
}: Readonly<FormActionsProps>) {
  const { t } = useTranslation('common');
  let defaultSubmitLabel = t('formActions.save');
  if (isEditing === true) defaultSubmitLabel = t('formActions.update');
  else if (isEditing === false) defaultSubmitLabel = t('formActions.create');
  const finalSubmitLabel = submitLabel || defaultSubmitLabel;
  const finalSubmittingLabel = submittingLabel ?? t('formActions.saving');
  const finalCancelLabel = cancelLabel ?? t('formActions.cancel');

  return (
    <div className={`flex items-center justify-end gap-3 pt-4 border-t border-line dark:border-line-dark ${containerClassName}`}>
      {showCancel && (
        <ButtonApp
          label={finalCancelLabel}
          type="button"
          onClick={onCancel}
          disabled={isSubmitting}
          variant="secondary"
          size="medium"
          className={cancelClassName}
        />
      )}
      <ButtonApp
        label={isSubmitting ? finalSubmittingLabel : finalSubmitLabel}
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
