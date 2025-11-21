interface FormActionsProps {
  onCancel: () => void;
  isSubmitting: boolean;
  isEditing: boolean;
  submitLabel?: string;
  cancelLabel?: string;
  submitButtonColor?: 'blue' | 'green' | 'purple';
}

function FormActions({ 
  onCancel, 
  isSubmitting, 
  isEditing,
  submitLabel,
  cancelLabel = 'Cancel',
  submitButtonColor = 'blue'
}: Readonly<FormActionsProps>) {
  const colorClasses = {
    blue: 'bg-blue-600 hover:bg-blue-700 disabled:bg-blue-400',
    green: 'bg-green-600 hover:bg-green-700 disabled:bg-green-400',
    purple: 'bg-purple-600 hover:bg-purple-700 disabled:bg-purple-400'
  };

  const defaultSubmitLabel = isEditing ? 'Update' : 'Create';
  const finalSubmitLabel = submitLabel || defaultSubmitLabel;

  return (
    <div className="flex items-center justify-end space-x-3 pt-4 border-t border-gray-200">
      <button
        type="button"
        onClick={onCancel}
        className="px-4 py-2 text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors"
        disabled={isSubmitting}
      >
        {cancelLabel}
      </button>
      <button
        type="submit"
        disabled={isSubmitting}
        className={`px-6 py-2 ${colorClasses[submitButtonColor]} text-white rounded-lg flex items-center transition-colors`}
      >
        {isSubmitting && (
          <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
        )}
        {isSubmitting ? 'Saving...' : finalSubmitLabel}
      </button>
    </div>
  );
}

export default FormActions;
