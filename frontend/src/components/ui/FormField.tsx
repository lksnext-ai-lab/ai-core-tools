import React from 'react';

interface FormFieldProps {
  label?: React.ReactNode;
  id: string;
  type?: 'text' | 'email' | 'password' | 'number' | 'url' | 'tel' | 'time' | 'file' | 'date' | 'radio' | 'checkbox';
  name?: string;
  ariaLabel?: string;
  value?: string | number;
  checked?: boolean;
  accept?: string;
  autoComplete?: string;
  ariaDescribedBy?: string;
  'data-lpignore'?: string;
  onChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  onFocus?: (e: React.FocusEvent<HTMLInputElement>) => void;
  onBlur?: (e: React.FocusEvent<HTMLInputElement>) => void;
  onKeyDown?: (e: React.KeyboardEvent<HTMLInputElement>) => void;
  min?: number;
  max?: number;
  step?: number;
  maxLength?: number;
  pattern?: string;
  placeholder?: string;
  disabled?: boolean;
  required?: boolean;
  error?: string;
  helpText?: string;
  className?: string;
  inputClassName?: string;
  labelClassName?: string;
  ref?: React.Ref<HTMLInputElement>;
}

/**
 * Reusable form field component with label, input, and error display
 */
export function FormField({
  label,
  id,
  type = 'text',
  name,
  ariaLabel,
  value,
  checked,
  accept,
  autoComplete,
  ariaDescribedBy,
  'data-lpignore': dataLpignore,
  onChange,
  onFocus,
  onBlur,
  onKeyDown,
  min,
  max,
  step,
  maxLength,
  pattern,
  placeholder,
  disabled = false,
  required = false,
  error,
  helpText,
  className = '',
  inputClassName = '',
  labelClassName = 'block text-sm font-medium text-fg dark:text-fg-dark mb-1',
  ref
}: Readonly<FormFieldProps>) {
  const inlineLabel = type === 'radio' || type === 'checkbox';
  const helpTextId = helpText && !error ? `${id}-help` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  const describedBy = [ariaDescribedBy, errorId, helpTextId].filter(Boolean).join(' ') || undefined;
  const inputBaseClassName = type === 'radio' || type === 'checkbox'
    ? 'h-4 w-4 shrink-0 accent-ink dark:accent-ink-dark border-line-strong rounded focus:outline-none focus-visible:outline focus-visible:outline-1 focus-visible:outline-offset-0 focus-visible:outline-accent disabled:opacity-50 disabled:cursor-not-allowed'
    : type === 'file'
    ? 'block w-full text-sm text-fg-secondary dark:text-fg-secondary-dark file:mr-3 file:py-2 file:px-4 file:rounded-md file:border file:border-ink file:text-sm file:font-medium file:bg-surface file:text-fg hover:file:bg-surface-hover dark:file:border-ink-dark dark:file:bg-surface-dark dark:file:text-fg-dark dark:hover:file:bg-surface-hover-dark disabled:opacity-50 disabled:cursor-not-allowed'
    : 'w-full px-3 py-2 text-sm border rounded-lg bg-surface text-fg placeholder:text-fg-faint dark:bg-surface-dark dark:text-fg-dark dark:placeholder:text-fg-faint-dark';
  const resolvedLabelClassName = labelClassName ?? (inlineLabel
    ? 'text-sm font-medium text-fg dark:text-fg-dark'
    : 'block text-sm font-medium text-fg dark:text-fg-dark mb-1');

  return (
    <div className={className}>
      {label !== undefined && !inlineLabel && (
        <label
          htmlFor={id}
          className={resolvedLabelClassName}
        >
          {label}
          {required && <span className="text-error dark:text-error-dark ml-1">*</span>}
        </label>
      )}

      <input
        ref={ref}
        id={id}
        name={name ?? id}
        type={type}
        {...(type === 'file' ? {} : { value })}
        checked={checked}
        aria-label={ariaLabel}
        accept={accept}
        autoComplete={autoComplete}
        data-lpignore={dataLpignore}
        onChange={onChange}
        onFocus={onFocus}
        onBlur={onBlur}
        onKeyDown={onKeyDown}
        min={min}
        max={max}
        step={step}
        maxLength={maxLength}
        pattern={pattern}
        placeholder={placeholder}
        disabled={disabled}
        required={required}
        aria-invalid={!!error}
        aria-describedby={describedBy}
        className={`${inputBaseClassName} ${
          error
            ? 'border-error focus:outline-none focus:border-error dark:border-error-dark dark:focus:border-error-dark'
            : 'focus:outline-none focus:border-accent dark:border-line-strong-dark dark:focus:border-accent'
        } ${
          disabled && type !== 'file' && !inlineLabel ? 'bg-surface-hover text-fg-tertiary cursor-not-allowed dark:bg-surface-hover-dark dark:text-fg-tertiary-dark' : ''
        } ${inputClassName}`}
      />

      {label !== undefined && inlineLabel && (
        <label htmlFor={id} className={resolvedLabelClassName}>
          {label}
          {required && <span className="text-error dark:text-error-dark ml-1">*</span>}
        </label>
      )}

      {helpText && !error && (
        <p id={helpTextId} className="mt-1 text-xs text-fg-tertiary dark:text-fg-tertiary-dark">{helpText}</p>
      )}

      {error && (
        <p id={errorId} className="mt-1 text-xs text-error dark:text-error-dark">{error}</p>
      )}
    </div>
  );
}

interface FormTextAreaProps {
  label: string;
  id: string;
  value: string;
  onChange: (e: React.ChangeEvent<HTMLTextAreaElement>) => void;
  maxLength?: number;
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
  maxLength,
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
        maxLength={maxLength}
        placeholder={placeholder}
        disabled={disabled}
        required={required}
        rows={rows}
        aria-invalid={!!error}
        aria-describedby={describedBy}
        className={`w-full px-3 py-2 text-sm border rounded-lg bg-surface text-fg placeholder:text-fg-faint dark:bg-surface-dark dark:text-fg-dark dark:placeholder:text-fg-faint-dark ${
          error
            ? 'border-error focus:outline-none focus:border-error dark:border-error-dark dark:focus:border-error-dark'
            : 'focus:outline-none focus:border-accent dark:border-line-strong-dark dark:focus:border-accent'
        } ${
          disabled ? 'bg-surface-hover text-fg-tertiary cursor-not-allowed dark:bg-surface-hover-dark dark:text-fg-tertiary-dark' : ''
        } ${textareaClassName}`}
      />

      {helpText && !error && (
        <p id={helpTextId} className="mt-1 text-xs text-fg-tertiary dark:text-fg-tertiary-dark">{helpText}</p>
      )}

      {error && (
        <p id={errorId} className="mt-1 text-xs text-error dark:text-error-dark">{error}</p>
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
  helpText?: React.ReactNode;
  ariaDescribedBy?: string;
  className?: string;
  labelClassName?: string;
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
  ariaDescribedBy,
  className = '',
  labelClassName = 'block text-sm font-medium text-fg dark:text-fg-dark mb-1'
}: Readonly<FormSelectProps>) {
  const helpTextId = helpText && !error ? `${id}-help` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  const describedBy = [ariaDescribedBy, errorId, helpTextId].filter(Boolean).join(' ') || undefined;

  return (
    <div className={className}>
      <label
        htmlFor={id}
        className={labelClassName}
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
        className={`w-full px-3 py-2 marketplace-filter-select border rounded-lg text-sm bg-surface text-fg dark:bg-surface-dark dark:text-fg-dark focus:outline-none ${
          error
            ? 'border-error focus:border-error dark:border-error-dark dark:focus:border-error-dark'
            : 'border-line-strong focus:border-accent dark:border-line-strong-dark dark:focus:border-accent'
        } ${
          disabled ? 'bg-surface-hover text-fg-tertiary cursor-not-allowed dark:bg-surface-hover-dark dark:text-fg-tertiary-dark' : ''
        }`}
      >
        {options.map(option => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>

      {helpText && !error && (
        <p id={helpTextId} className="mt-1 text-xs text-fg-tertiary dark:text-fg-tertiary-dark">{helpText}</p>
      )}

      {error && (
        <p id={errorId} className="mt-1 text-xs text-error dark:text-error-dark">{error}</p>
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
  ariaDescribedBy?: string;
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
  ariaDescribedBy,
  className = ''
}: Readonly<FormCheckboxProps>) {
  const helpTextId = helpText ? `${id}-help` : undefined;
  const describedBy = [ariaDescribedBy, helpTextId].filter(Boolean).join(' ') || undefined;

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
          aria-describedby={describedBy}
          className="w-4 h-4 accent-ink dark:accent-ink-dark border-line-strong rounded focus:outline-none focus-visible:outline focus-visible:outline-1 focus-visible:outline-offset-0 focus-visible:outline-accent disabled:opacity-50 disabled:cursor-not-allowed"
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
          <p id={helpTextId} className="text-xs text-fg-tertiary dark:text-fg-tertiary-dark">{helpText}</p>
        )}
      </div>
    </div>
  );
}

interface FormRadioProps {
  label: string;
  checked: boolean;
  onChange: () => void;
  className?: string;
}

/**
 * Reusable radio option (label + native radio). Group several inside a fieldset/legend.
 */
export function FormRadio({
  label,
  checked,
  onChange,
  className = '',
}: Readonly<FormRadioProps>) {
  return (
    <label className={`text-fg dark:text-fg-dark ${className}`}>
      <input type="radio" checked={checked} onChange={onChange} className="w-4 h-4 accent-ink dark:accent-ink-dark" />
      {label}
    </label>
  );
}

export default FormField;

