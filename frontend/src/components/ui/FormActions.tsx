import React from 'react';

interface FormActionsProps {
  onCancel: () => void;
  isSubmitting: boolean;
  submitLabel?: string;
  cancelLabel?: string;
  submitClassName?: string;
  cancelClassName?: string;
  containerClassName?: string;
  showCancel?: boolean;
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
  showCancel = true
}: FormActionsProps) {
  return (
    <div className={`flex justify-end space-x-3 pt-4 border-t border-gray-200 ${containerClassName}`}>
      {showCancel && (
        <button
          type="button"
          onClick={onCancel}
          disabled={isSubmitting}
          className={`px-4 py-2 border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors ${cancelClassName}`}
        >
          {cancelLabel}
        </button>
      )}
      
      <button
        type="submit"
        disabled={isSubmitting}
        className={`px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center ${submitClassName}`}
      >
        {isSubmitting && (
          <svg 
            className="animate-spin -ml-1 mr-2 h-4 w-4 text-white" 
            xmlns="http://www.w3.org/2000/svg" 
            fill="none" 
            viewBox="0 0 24 24"
          >
            <circle 
              className="opacity-25" 
              cx="12" 
              cy="12" 
              r="10" 
              stroke="currentColor" 
              strokeWidth="4"
            />
            <path 
              className="opacity-75" 
              fill="currentColor" 
              d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
            />
          </svg>
        )}
        {isSubmitting ? 'Saving...' : submitLabel}
      </button>
    </div>
  );
}

export default FormActions;

