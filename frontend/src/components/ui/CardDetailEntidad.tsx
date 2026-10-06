import type { KeyboardEvent, MouseEvent, ReactNode } from 'react';

export interface CardDetailEntidadProps {
  readonly title: string;
  readonly description?: string;
  readonly badges?: ReadonlyArray<{
    readonly text: string;
    readonly color?: string;
    readonly className?: string;
  }>;
  readonly table?: ReadonlyArray<{
    readonly label: string;
    readonly value: ReactNode;
  }>;
  readonly metadata?: ReactNode;
  readonly topRight?: ReactNode;
  readonly imageSrc?: string;
  readonly imageAlt?: string;
  readonly badgeText?: string;
  readonly onClick?: () => void;
  readonly actionLabel?: string;
  readonly onActionClick?: () => void;
  readonly actionDisabled?: boolean;
  readonly className?: string;
}

function handleCardKeyDown(event: KeyboardEvent<HTMLElement>, onClick?: () => void) {
  if (!onClick || (event.key !== 'Enter' && event.key !== ' ')) return;

  event.preventDefault();
  onClick();
}

function handleActionClick(event: MouseEvent<HTMLButtonElement>, onActionClick?: () => void) {
  event.stopPropagation();
  onActionClick?.();
}

/** Reusable entity card for recent apps, marketplace items, and owned apps. */
export function CardDetailEntidad({
  title,
  description,
  badges = [],
  table,
  metadata,  /*texto por debajo de la linea*/
  topRight, /*elemento en la esquina superior derecha, Acepta cualquier ReactNode, por ejemplo una etiqueta de ro*/
  imageSrc, /*imagen dentro del recuadro*/
  imageAlt = '',
  badgeText, /*texto dentro del recuadro*/
  onClick,
  actionLabel,
  onActionClick,
  actionDisabled = false,
  className = '',
}: CardDetailEntidadProps) {
  const isClickable = Boolean(onClick);

  return (
    <button
      className={`group flex h-full flex-col rounded-md bg-surface-ash dark:bg-btCard-dark p-5 text-left  ${
        isClickable ? 'cursor-pointer' : ''
      } ${className}`}
      role={isClickable ? 'button' : undefined}
      tabIndex={isClickable ? 0 : undefined}
      onClick={onClick}
      onKeyDown={(event) => handleCardKeyDown(event, onClick)}
    >
      <div className="mb-3 flex items-start justify-between gap-3">
        <div className="flex h-[34px] w-[34px] shrink-0 items-center justify-center overflow-hidden rounded-md border-[0.8px] border-[#FF682C] text-sm font-medium ">
          {imageSrc ? (
            <img src={imageSrc} alt={imageAlt} className="h-full w-full object-cover" />
          ) : (
            badgeText
          )}
        </div>
        {topRight && <div className="min-w-0">{topRight}</div>}
      </div>

      <h3 className="mb-1 font-display text-lg font-normal tracking-[-0.02em] text-ink dark:text-ink-dark">
        {title}
      </h3>
      {description && (
        <p className="mb-4 text-[13.5px] leading-[1.45] text-fg-secondary dark:text-fg-secondary-dark">
          {description}
        </p>
      )}

      {badges.length > 0 && (
        <div className="mb-4 flex flex-wrap gap-2">
          {badges.map((badge) => (
            <span
              key={badge.text}
              className={`rounded-full px-2.5 py-1 text-xs font-medium ${badge.className ?? ''}`}
              style={{
                ...(badge.color ? { backgroundColor: badge.color, color: '#ffffff' } : {}),
              }}
            >
              {badge.text}
            </span>
          ))}
        </div>
      )}

      {table !== undefined ? (
        <div className="mt-auto overflow-x-auto border-t border-[#e0ddd6] pt-2 dark:border-line-dark">
          <table className="table-fixed text-center leading-none">
            <thead>
              <tr>
                {table.map((column, index) => (
                  <th
                    key={`label-${column.label}`}
                    className={`px-2 py-0 text-[8px] font-medium uppercase tracking-[0.04em] text-fg-tertiary dark:text-fg-tertiary-dark ${
                      index < table.length - 1 ? 'border-r border-[#e0ddd6] dark:border-line-dark' : ''
                    }`}
                  >
                    {column.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              <tr>
                {table.map((column, index) => (
                  <td
                    key={`value-${column.label}`}
                    className={`px-2 py-0 text-sm font-semibold text-ink dark:text-ink-dark ${
                      index < table.length - 1 ? 'border-r border-[#e0ddd6] dark:border-line-dark' : ''
                    }`}
                  >
                    {column.value}
                  </td>
                ))}
              </tr>
            </tbody>
          </table>
        </div>
      ) : (metadata || actionLabel) && (
        <div className="mt-auto flex items-center gap-3 border-t border-[#e0ddd6] pt-3 text-xs text-fg-tertiary dark:border-line-dark dark:text-fg-tertiary-dark">
          {metadata && <div className="min-w-0 flex-1">{metadata}</div>}
          {actionLabel && (
            <button
              type="button"
              onClick={(event) => handleActionClick(event, onActionClick)}
              onKeyDown={(event) => event.stopPropagation()}
              disabled={actionDisabled}
              className="shrink-0 bg-ink px-3 py-2 font-display rounded-md text-sm font-normal text-ink-on transition-colors hover:bg-[#383838] disabled:cursor-not-allowed disabled:opacity-50 dark:bg-ink-dark dark:text-ink-on-dark dark:hover:bg-[#d8d3c8]"
            >
              {actionLabel}
            </button>
          )}
        </div>
      )}
    </button>
  );
}

export default CardDetailEntidad;