import React from 'react';

interface FormFieldProps {
  label: string;
  id: string;
  type?: 'text' | 'email' | 'password' | 'number' | 'url' | 'tel';
  value: string | number;
  onChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  placeholder?: string;
  disabled?: boolean;
  required?: boolean;
  error?: string;
  helpText?: string;
  className?: string;
  inputClassName?: string;
}

/**
 * Reusable form field component with label, input, and error display
 */
export function FormField({
  label,
  id,
  type = 'text',
  value,
  onChange,
  placeholder,
  disabled = false,
  required = false,
  error,
  helpText,
  className = '',
  inputClassName = ''
}: Readonly<FormFieldProps>) {
  const helpTextId = helpText && !error ? `${id}-help` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  const describedBy = [errorId, helpTextId].filter(Boolean).join(' ') || undefined;

  return (
    <div className={className}>
      <label
        htmlFor={id}
        className="block text-sm font-medium text-fg dark:text-fg-dark mb-1"
      >
        {label}
        {required && <span className="text-error dark:text-error-dark ml-1">*</span>}
      </label>

      <input
        id={id}
        name={id}
        type={type}
        value={value}
        onChange={onChange}
        placeholder={placeholder}
        disabled={disabled}
        required={required}
        aria-invalid={!!error}
        aria-describedby={describedBy}
        className={`w-full px-3 py-2 text-sm border rounded-lg bg-surface text-fg placeholder:text-fg-faint dark:bg-surface-dark dark:text-fg-dark dark:placeholder:text-fg-faint-dark  ${
          error
            ? 'border-error focus:ring-error focus:border-error dark:border-error-dark dark:focus:ring-error-dark dark:focus:border-error-dark'
            : 'focus:outline-none focus:border-accent dark:border-line-strong-dark dark:focus:border-accent'
        } ${
          disabled ? 'bg-surface-hover text-fg-tertiary cursor-not-allowed dark:bg-surface-hover-dark dark:text-fg-tertiary-dark' : ''
        } ${inputClassName}`}
      />

      {helpText && !error && (
        <p id={helpTextId} className="mt-1 text-sm text-fg-tertiary dark:text-fg-tertiary-dark">{helpText}</p>
      )}

      {error && (
        <p id={errorId} className="mt-1 text-sm text-error dark:text-error-dark">{error}</p>
      )}
    </div>
  );
}

interface FormTextAreaProps {
  label: string;
  id: string;
  value: string;
  onChange: (e: React.ChangeEvent<HTMLTextAreaElement>) => void;
  placeholder?: string;
  disabled?: boolean;
  required?: boolean;
  error?: string;
  helpText?: string;
  rows?: number;
  className?: string;
  textareaClassName?: string;
}

/**
 * Reusable textarea field component
 */
export function FormTextArea({
  label,
  id,
  value,
  onChange,
  placeholder,
  disabled = false,
  required = false,
  error,
  helpText,
  rows = 3,
  className = '',
  textareaClassName = ''
}: Readonly<FormTextAreaProps>) {
  const helpTextId = helpText && !error ? `${id}-help` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  const describedBy = [errorId, helpTextId].filter(Boolean).join(' ') || undefined;

  return (
    <div className={className}>
      <label
        htmlFor={id}
        className="block text-sm font-medium text-fg dark:text-fg-dark mb-1"
      >
        {label}
        {required && <span className="text-error dark:text-error-dark ml-1">*</span>}
      </label>

      <textarea
        id={id}
        name={id}
        value={value}
        onChange={onChange}
        placeholder={placeholder}
        disabled={disabled}
        required={required}
        rows={rows}
        aria-invalid={!!error}
        aria-describedby={describedBy}
        className={`w-full px-3 py-2 text-sm border rounded-lg bg-surface text-fg placeholder:text-fg-faint dark:bg-surface-dark dark:text-fg-dark dark:placeholder:text-fg-faint-dark focus:outline-none focus:ring-1 transition-colors ${
          error
            ? 'border-error focus:ring-error focus:border-error dark:border-error-dark dark:focus:ring-error-dark dark:focus:border-error-dark'
            : 'border-line-strong focus:ring-ink focus:border-ink dark:border-line-strong-dark dark:focus:ring-ink-dark dark:focus:border-ink-dark'
        } ${
          disabled ? 'bg-surface-hover text-fg-tertiary cursor-not-allowed dark:bg-surface-hover-dark dark:text-fg-tertiary-dark' : ''
        } ${textareaClassName}`}
      />

      {helpText && !error && (
        <p id={helpTextId} className="mt-1 text-sm text-fg-tertiary dark:text-fg-tertiary-dark">{helpText}</p>
      )}

      {error && (
        <p id={errorId} className="mt-1 text-sm text-error dark:text-error-dark">{error}</p>
      )}
    </div>
  );
}

interface FormSelectProps {
  label: string;
  id: string;
  value: string | number;
  onChange: (e: React.ChangeEvent<HTMLSelectElement>) => void;
  options: Array<{ value: string | number; label: string }>;
  disabled?: boolean;
  required?: boolean;
  error?: string;
  helpText?: string;
  className?: string;
  selectClassName?: string;
}

/**
 * Reusable select field component
 */
export function FormSelect({
  label,
  id,
  value,
  onChange,
  options,
  disabled = false,
  required = false,
  error,
  helpText,
  className = '',
  selectClassName = ''
}: Readonly<FormSelectProps>) {
  const helpTextId = helpText && !error ? `${id}-help` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  const describedBy = [errorId, helpTextId].filter(Boolean).join(' ') || undefined;

  return (
    <div className={className}>
      <label
        htmlFor={id}
        className="block text-sm font-medium text-fg dark:text-fg-dark mb-1"
      >
        {label}
        {required && <span className="text-error dark:text-error-dark ml-1">*</span>}
      </label>

      <select
        id={id}
        name={id}
        value={value}
        onChange={onChange}
        disabled={disabled}
        required={required}
        aria-invalid={!!error}
        aria-describedby={describedBy}
        className={`w-full px-3 py-2 marketplace-filter-select border border-gray-300 dark:border-btCard-border-dark dark:bg-surface-dark focus:outline-none focus:border-accent rounded-lg text-sm ${
          error
            ? 'border-error focus:ring-error focus:border-error dark:border-error-dark dark:focus:ring-error-dark dark:focus:border-error-dark'
            : 'border-gray-300  focus:border-accent dark:border-btCard-border-dark dark:focus:border-accent '
        } ${
          disabled ? 'bg-surface-hover text-fg-tertiary cursor-not-allowed dark:bg-surface-hover-dark dark:text-fg-tertiary-dark' : ''
        } ${selectClassName}`}
      >
        {options.map(option => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>


      

      {helpText && !error && (
        <p id={helpTextId} className="mt-1 text-sm text-fg-tertiary dark:text-fg-tertiary-dark">{helpText}</p>
      )}

      {error && (
        <p id={errorId} className="mt-1 text-sm text-error dark:text-error-dark">{error}</p>
      )}
    </div>
  );
}

interface FormCheckboxProps {
  label: string;
  id: string;
  checked: boolean;
  onChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  disabled?: boolean;
  helpText?: string;
  className?: string;
}

/**
 * Reusable checkbox field component
 */
export function FormCheckbox({
  label,
  id,
  checked,
  onChange,
  disabled = false,
  helpText,
  className = ''
}: Readonly<FormCheckboxProps>) {
  return (
    <div className={`flex items-start ${className}`}>
      <div className="flex items-center h-5">
        <input
          id={id}
          name={id}
          type="checkbox"
          checked={checked}
          onChange={onChange}
          disabled={disabled}
          className="w-4 h-4 accent-ink dark:accent-ink-dark border-line-strong rounded focus-visible:ring-2 focus-visible:ring-focus dark:focus-visible:ring-focus-dark disabled:opacity-50 disabled:cursor-not-allowed"
        />
      </div>
      <div className="ml-3">
        <label
          htmlFor={id}
          className="text-sm font-medium text-fg dark:text-fg-dark"
        >
          {label}
        </label>
        {helpText && (
          <p className="text-sm text-fg-tertiary dark:text-fg-tertiary-dark">{helpText}</p>
        )}
      </div>
    </div>
  );
}

export default FormField;

