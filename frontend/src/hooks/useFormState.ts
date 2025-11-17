import { useState } from 'react';

/**
 * Custom hook for managing form state, submission, and errors
 * Eliminates repetitive form state management code across all forms
 */
export function useFormState<T>(initialData: T) {
  const [formData, setFormData] = useState<T>(initialData);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  /**
   * Handle form submission with automatic error handling
   * @param e - Form event
   * @param onSubmit - Async submit handler
   * @param errorMessage - Custom error message (optional)
   */
  const handleSubmit = async (
    e: React.FormEvent,
    onSubmit: (data: T) => Promise<void>,
    errorMessage?: string
  ) => {
    e.preventDefault();
    
    try {
      setIsSubmitting(true);
      setError(null);
      await onSubmit(formData);
    } catch (err) {
      const defaultMessage = errorMessage || 'Failed to save';
      setError(err instanceof Error ? err.message : defaultMessage);
      throw err; // Re-throw so caller can handle if needed
    } finally {
      setIsSubmitting(false);
    }
  };

  /**
   * Update a single field in the form data
   */
  const updateField = <K extends keyof T>(field: K, value: T[K]) => {
    setFormData(prev => ({
      ...prev,
      [field]: value
    }));
  };

  /**
   * Update multiple fields at once
   */
  const updateFields = (updates: Partial<T>) => {
    setFormData(prev => ({
      ...prev,
      ...updates
    }));
  };

  /**
   * Reset form to initial state
   */
  const reset = () => {
    setFormData(initialData);
    setError(null);
    setIsSubmitting(false);
  };

  /**
   * Clear error message
   */
  const clearError = () => {
    setError(null);
  };

  return {
    formData,
    setFormData,
    isSubmitting,
    error,
    setError,
    handleSubmit,
    updateField,
    updateFields,
    reset,
    clearError
  };
}

