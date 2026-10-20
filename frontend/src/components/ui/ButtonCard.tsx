import type { ReactNode } from 'react';
import { FormField } from './FormField';

export type ButtonCardVariant = 'default' | 'selectable' | 'selectable-radio';

export interface ButtonCardProps {
  readonly children: ReactNode;
  readonly onClick: () => void;
  readonly ariaLabel?: string;
  readonly variant?: ButtonCardVariant;
  readonly selected?: boolean;
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
  variant = 'default',
  selected = false,
  interactiveChildren = false,
  radioName,
  radioValue,
  className = '',
}: ButtonCardProps) {
  const radioVariant = variant === 'selectable-radio';
  const selectableClassName = selected
    ? 'bg-surface-hover dark:bg-btCard-hover border-2 border-bg-soft dark:border-bronze-border-dark'
    : 'bg-surface dark:bg-surface-dark border border-line dark:border-line-dark';
  const variantClassName = variant === 'selectable' || radioVariant
    ? `rounded-md p-3 transition-colors ${selectableClassName}`
    : 'rounded-md bg-surface-ash p-5 dark:bg-btCard-dark';
  const interactiveChildrenClassName = interactiveChildren || radioVariant
    ? '[&_input]:pointer-events-auto [&_button]:pointer-events-auto [&_label]:pointer-events-auto [&_select]:pointer-events-auto [&_textarea]:pointer-events-auto'
    : '';

  return (
    <div
      className={`group relative flex h-full flex-col text-left ${variantClassName} ${className}`}
    >
      <button
        type="button"
        onClick={() => {
          if (!radioVariant || !selected) onClick();
        }}
        aria-label={ariaLabel}
        aria-pressed={variant === 'selectable' ? selected : undefined}
        aria-hidden={radioVariant}
        tabIndex={radioVariant ? -1 : undefined}
        className="absolute inset-0 z-0 h-full w-full cursor-pointer rounded-md outline-none focus-visible:outline-none"
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
        {radioVariant ? <div className="min-w-0 flex-1">{children}</div> : children}
      </div>
    </div>
  );
}

export default ButtonCard;
