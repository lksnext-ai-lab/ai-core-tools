import React from 'react';

interface FormFieldProps {
  label?: React.ReactNode;
  id: string;
  type?: 'text' | 'email' | 'password' | 'number' | 'url' | 'tel' | 'time' | 'file' | 'date' | 'radio' | 'checkbox';
  name?: string;
  ariaLabel?: string;
  ariaInvalid?: boolean;
  ariaRequired?: boolean;
  ariaHidden?: boolean;
  tabIndex?: number;
  value?: string | number;
  checked?: boolean;
  accept?: string;
  autoComplete?: string;
  inputMode?: React.InputHTMLAttributes<HTMLInputElement>['inputMode'];
  ariaDescribedBy?: string;
  role?: string;
  ariaExpanded?: boolean;
  ariaControls?: string;
  ariaActiveDescendant?: string;
  'data-lpignore'?: string;
  'data-form-type'?: string;
  onChange?: (e: React.ChangeEvent<HTMLInputElement>) => void;
  onFocus?: (e: React.FocusEvent<HTMLInputElement>) => void;
  onBlur?: (e: React.FocusEvent<HTMLInputElement>) => void;
  onKeyDown?: (e: React.KeyboardEvent<HTMLInputElement>) => void;
  min?: number;
  max?: number;
  step?: number;
  maxLength?: number;
  pattern?: string;
  placeholder?: string;
  readOnly?: boolean;
  disabled?: boolean;
  required?: boolean;
  error?: string;
  helpText?: React.ReactNode;
  helpTextAriaLive?: 'off' | 'polite' | 'assertive';
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
  ariaInvalid,
  ariaRequired,
  ariaHidden,
  tabIndex,
  value,
  checked,
  accept,
  autoComplete,
  inputMode,
  ariaDescribedBy,
  role,
  ariaExpanded,
  ariaControls,
  ariaActiveDescendant,
  'data-lpignore': dataLpignore,
  'data-form-type': dataFormType,
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
  readOnly = false,
  disabled = false,
  required = false,
  error,
  helpText,
  helpTextAriaLive,
  className = '',
  inputClassName = '',
  labelClassName = 'block text-sm font-medium text-fg dark:text-fg-dark mb-1',
  ref
}: Readonly<FormFieldProps>) {
  const [selectedFileName, setSelectedFileName] = React.useState('');
  const inlineLabel = type === 'radio' || type === 'checkbox';
  const helpTextId = helpText && !error ? `${id}-help` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  const describedBy = [ariaDescribedBy, errorId, helpTextId].filter(Boolean).join(' ') || undefined;
  const handleInputChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    if (type === 'file') {
      setSelectedFileName(event.target.files?.[0]?.name ?? '');
    }
    onChange?.(event);
  };
  const inputBaseClassName = type === 'radio' || type === 'checkbox'
    ? 'h-4 w-4 shrink-0 accent-ink dark:accent-ink-dark border-line-strong rounded focus:outline-none focus-visible:outline focus-visible:outline-1 focus-visible:outline-offset-0 focus-visible:outline-accent disabled:opacity-50 disabled:cursor-not-allowed'
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

      {type === 'file' ? (
        <div
          className={`group relative flex min-h-10 w-full items-center overflow-hidden rounded-lg border bg-surface text-sm dark:bg-surface-dark ${
            error
              ? 'border-error dark:border-error-dark'
              : 'border-line-strong focus-within:border-accent dark:border-line-strong-dark'
          } ${
            disabled ? 'bg-surface-hover text-fg-tertiary dark:bg-surface-hover-dark dark:text-fg-tertiary-dark' : 'text-fg-secondary dark:text-fg-secondary-dark'
          } ${inputClassName}`}
        >
          <span className="min-w-0 flex-1 truncate px-3">
            {selectedFileName || 'No file selected'}
          </span>
          <span
            className={`inline-flex min-h-10 shrink-0 items-center justify-center border-l border-transparent bg-ink px-4 font-display font-normal tracking-[-0.02em] text-ink-on transition-colors dark:bg-ink-dark dark:text-ink-on-dark ${
              disabled ? 'opacity-50' : 'group-hover:bg-ink-hover dark:group-hover:bg-ink-hover-dark'
            }`}
          >
            Choose file
          </span>
          <input
            ref={ref}
            id={id}
            name={name ?? id}
            type={type}
            accept={accept}
            aria-label={ariaLabel}
            aria-hidden={ariaHidden}
            tabIndex={tabIndex}
            inputMode={inputMode}
            data-lpignore={dataLpignore}
            data-form-type={dataFormType}
            onChange={handleInputChange}
            onFocus={onFocus}
            onBlur={onBlur}
            onKeyDown={onKeyDown}
            disabled={disabled}
            required={required}
            aria-invalid={!!error}
            aria-describedby={describedBy}
            className="absolute inset-0 h-full w-full cursor-pointer opacity-0 disabled:cursor-not-allowed"
          />
        </div>
      ) : (
        <input
          ref={ref}
          id={id}
          name={name ?? id}
          type={type}
          value={value}
          checked={checked}
          aria-label={ariaLabel}
          aria-hidden={ariaHidden}
          tabIndex={tabIndex}
          inputMode={inputMode}
          role={role}
          aria-expanded={ariaExpanded}
          aria-controls={ariaControls}
          aria-activedescendant={ariaActiveDescendant}
          autoComplete={autoComplete}
          data-lpignore={dataLpignore}
          data-form-type={dataFormType}
          onChange={handleInputChange}
          onFocus={onFocus}
          onBlur={onBlur}
          onKeyDown={onKeyDown}
          min={min}
          max={max}
          step={step}
          maxLength={maxLength}
          pattern={pattern}
          placeholder={placeholder}
          readOnly={readOnly}
          disabled={disabled}
          required={required}
          aria-invalid={ariaInvalid ?? !!error}
          aria-required={ariaRequired ?? required}
          aria-describedby={describedBy}
          className={`${inputBaseClassName} ${
            error
              ? 'border-error focus:outline-none focus:border-error dark:border-error-dark dark:focus:border-error-dark'
              : 'focus:outline-none focus:border-accent dark:border-line-strong-dark dark:focus:border-accent'
          } ${
            disabled && !inlineLabel ? 'bg-surface-hover text-fg-tertiary cursor-not-allowed dark:bg-surface-hover-dark dark:text-fg-tertiary-dark' : ''
          } ${inputClassName}`}
        />
      )}

      {label !== undefined && inlineLabel && (
        <label htmlFor={id} className={resolvedLabelClassName}>
          {label}
          {required && <span className="text-error dark:text-error-dark ml-1">*</span>}
        </label>
      )}

      {helpText && !error && (
        <p id={helpTextId} aria-live={helpTextAriaLive} className="mt-1 text-xs text-fg-tertiary dark:text-fg-tertiary-dark">{helpText}</p>
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
  ariaLabel?: string;
  ariaInvalid?: boolean;
  value: string;
  onChange: (e: React.ChangeEvent<HTMLTextAreaElement>) => void;
  maxLength?: number;
  placeholder?: string;
  ariaDescribedBy?: string;
  disabled?: boolean;
  required?: boolean;
  error?: string;
  helpText?: string;
  helpTextAriaLive?: 'off' | 'polite' | 'assertive';
  rows?: number;
  className?: string;
  textareaClassName?: string;
  labelClassName?: string;
  ref?: React.Ref<HTMLTextAreaElement>;
}

/**
 * Reusable textarea field component
 */
export function FormTextArea({
  label,
  id,
  ariaLabel,
  ariaInvalid,
  value,
  onChange,
  maxLength,
  placeholder,
  ariaDescribedBy,
  disabled = false,
  required = false,
  error,
  helpText,
  helpTextAriaLive,
  rows = 3,
  className = '',
  textareaClassName = '',
  labelClassName = 'block text-sm font-medium text-fg dark:text-fg-dark mb-1',
  ref
}: Readonly<FormTextAreaProps>) {
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

      <textarea
        ref={ref}
        id={id}
        name={id}
        aria-label={ariaLabel}
        value={value}
        onChange={onChange}
        maxLength={maxLength}
        placeholder={placeholder}
        disabled={disabled}
        required={required}
        rows={rows}
        aria-invalid={ariaInvalid ?? !!error}
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
        <p id={helpTextId} aria-live={helpTextAriaLive} className="mt-1 text-xs text-fg-tertiary dark:text-fg-tertiary-dark">{helpText}</p>
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
  title?: string;
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
  title,
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
        title={title}
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
  variant?: 'checkbox' | 'toggle';
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
  variant = 'checkbox',
  disabled = false,
  helpText,
  ariaDescribedBy,
  className = ''
}: Readonly<FormCheckboxProps>) {
  const helpTextId = helpText ? `${id}-help` : undefined;
  const describedBy = [ariaDescribedBy, helpTextId].filter(Boolean).join(' ') || undefined;

  if (variant === 'toggle') {
    return (
      <div className={`flex flex-col items-start ${className}`}>
        <div className="flex items-center">
          <input
            id={id}
            name={id}
            type="checkbox"
            checked={checked}
            onChange={onChange}
            disabled={disabled}
            aria-describedby={describedBy}
            className="sr-only peer"
          />
          <label
            htmlFor={id}
            className={`inline-flex items-center gap-3 rounded-full ${disabled ? 'cursor-not-allowed' : 'cursor-pointer'} peer-focus-visible:ring-2 peer-focus-visible:ring-focus dark:peer-focus-visible:ring-focus-dark`}
          >
            <span
              aria-hidden="true"
              className={`relative block h-5 w-9 rounded-full transition-colors ${
            checked
                  ? 'bg-fg dark:bg-fg-dark'
                  : 'bg-line-strong dark:bg-line-strong-dark'
              }`}
            >
              <span
                className={`absolute start-0.5 top-0.5 h-4 w-4 rounded-full border bg-surface dark:bg-surface-dark transition-transform ${
                  checked
                    ? 'translate-x-4 rtl:-translate-x-4 border-fg dark:border-fg-dark'
                    : 'translate-x-0 border-line-strong dark:border-line-strong-dark'
                }`}
              />
            </span>
            <span className="text-sm font-medium text-fg dark:text-fg-dark">{label}</span>
          </label>
        </div>
        {helpText && (
          <p id={helpTextId} className="ml-12 mt-1 text-xs text-fg-tertiary dark:text-fg-tertiary-dark">{helpText}</p>
        )}
      </div>
    );
  }

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
      <input
        type="radio"
        checked={checked}
        onChange={onChange}
        className="w-4 h-4 accent-ink dark:accent-ink-dark"
      />
      {label}
    </label>
  );
}

export default FormField;

