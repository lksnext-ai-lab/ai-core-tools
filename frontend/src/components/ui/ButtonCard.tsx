import { useId, type ReactNode } from 'react';
import { FormCheckbox, FormField } from './FormField';

export type ButtonCardVariant = 'default' | 'selectable' | 'selectable-radio' | 'selectable-check';

export interface ButtonCardProps {
  readonly children?: ReactNode;
  readonly onClick: () => void;
  readonly ariaLabel?: string;
  readonly disabled?: boolean;
  readonly variant?: ButtonCardVariant;
  readonly selected?: boolean;
  readonly checkboxLabel?: string;
  readonly checkboxHelpText?: string;
  readonly interactiveChildren?: boolean;
  readonly radioName?: string;
  readonly radioValue?: string;
  readonly className?: string;
}

/**
 * Whole-card button (apps grid, marketplace catalog). An invisible button covers the card;
 * the content ignores pointer events, so nested controls need `pointer-events-auto relative z-10`.
 */
export function ButtonCard({
  children,
  onClick,
  ariaLabel = 'Open card',
  disabled = false,
  variant = 'default',
  selected = false,
  checkboxLabel,
  checkboxHelpText,
  interactiveChildren = false,
  radioName,
  radioValue,
  className = '',
}: ButtonCardProps) {
  const checkboxId = useId();
  const radioVariant = variant === 'selectable-radio';
  const checkboxVariant = variant === 'selectable-check';
  const inputVariant = radioVariant || checkboxVariant;
  const selectableClassName = selected
    ? 'bg-surface-hover dark:bg-btCard-hover border-2 border-bg-soft dark:border-bronze-border-dark'
    : 'bg-surface dark:bg-surface-dark border border-line dark:border-line-dark';
  const variantClassName = variant === 'selectable' || inputVariant
    ? `rounded-md p-3 transition-colors ${selectableClassName}`
    : 'rounded-md bg-surface-ash p-5 dark:bg-btCard-dark';
  const interactiveChildrenClassName = interactiveChildren || inputVariant
    ? '[&_input]:pointer-events-auto [&_button]:pointer-events-auto [&_label]:pointer-events-auto [&_select]:pointer-events-auto [&_textarea]:pointer-events-auto'
    : '';

  return (
    <div
      className={`group relative flex h-full flex-col text-left ${variantClassName} ${className}`}
    >
      <button
        type="button"
        onClick={() => {
          if (!disabled && (!radioVariant || !selected)) onClick();
        }}
        disabled={disabled}
        aria-label={ariaLabel}
        aria-pressed={variant === 'selectable' ? selected : undefined}
        aria-hidden={inputVariant}
        tabIndex={inputVariant ? -1 : undefined}
        className="absolute inset-0 z-0 h-full w-full cursor-pointer rounded-md outline-none focus-visible:outline-none disabled:cursor-default"
      />
      <div className={`pointer-events-none relative z-10 flex min-h-0 flex-1 ${radioVariant ? 'flex-row items-start gap-3' : 'flex-col'} ${interactiveChildrenClassName}`}>
        {radioVariant && (
          <FormField
            id={`${radioName ?? 'button-card-radio'}-${radioValue ?? ariaLabel}`}
            name={radioName ?? 'button-card-radio'}
            type="radio"
            value={radioValue ?? ''}
            checked={selected}
            label={undefined}
            className="w-fit"
            inputClassName="mt-1 cursor-pointer"
            onChange={() => {
              if (!selected) onClick();
            }}
          />
        )}
        {checkboxVariant && (
          <FormCheckbox
            id={`button-card-checkbox-${checkboxId}`}
            label={checkboxLabel ?? ariaLabel}
            checked={selected}
            onChange={() => {
              if (!disabled) onClick();
            }}
            disabled={disabled}
            helpText={checkboxHelpText}
          />
        )}
        {radioVariant ? <div className="min-w-0 flex-1">{children}</div> : children}
      </div>
    </div>
  );
}

export default ButtonCard;
