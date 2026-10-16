import React from 'react';

import { Spinner } from './Spinner';

interface FormActionsProps {
  onCancel: () => void;
  isSubmitting: boolean;
  submitLabel?: string;
  cancelLabel?: string;
  submitClassName?: string;
  cancelClassName?: string;
  containerClassName?: string;
  showCancel?: boolean;
  submitDisabled?: boolean; // Additional condition to disable submit button
}

/**
 * Reusable form action buttons (Cancel/Submit)
 * Provides consistent button styling and behavior across all forms
 */
export function FormActions({
  onCancel,
  isSubmitting,
  submitLabel = 'Save',
  cancelLabel = 'Cancel',
  submitClassName = '',
  cancelClassName = '',
  containerClassName = '',
  showCancel = true,
  submitDisabled = false
}: Readonly<FormActionsProps>) {
  return (
    <div className={`flex justify-end space-x-3 pt-4 border-t border-line dark:border-line-dark ${containerClassName}`}>
      {showCancel && (
        <button
          type="button"
          onClick={onCancel}
          disabled={isSubmitting}
          className={`px-4 py-2 text-sm font-medium border border-line-strong rounded-lg text-fg bg-transparent hover:bg-surface-hover dark:border-line-strong-dark dark:text-fg-dark dark:hover:bg-surface-hover-dark focus:outline-none focus-visible:ring-2 focus-visible:ring-focus dark:focus-visible:ring-focus-dark disabled:opacity-50 disabled:cursor-not-allowed transition-colors ${cancelClassName}`}
        >
          {cancelLabel}
        </button>
      )}
      
      <button
        type="submit"
        disabled={isSubmitting || submitDisabled}
        className={`px-4 py-2 text-sm font-medium bg-ink text-ink-on rounded-lg hover:bg-ink/85 dark:bg-ink-dark dark:text-ink-on-dark dark:hover:bg-ink-dark/85 focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-focus dark:focus-visible:ring-focus-dark disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center ${submitClassName}`}
      >
        {isSubmitting && <Spinner size="sm" tone="current" className="mr-2" />}
        {isSubmitting ? 'Saving...' : submitLabel}
      </button>
    </div>
  );
}

export default FormActions;

