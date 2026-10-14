
import type { ReactNode } from 'react';
import { ButtonApp } from './ButtonApp';

/* =========================================================
   Types
========================================================= */

export interface CardStat {
  readonly label: string;
  readonly value: ReactNode;
}

interface CardBaseProps {
  // Header
  readonly titleCab?: string;
  readonly subTitleCab?: string;
  readonly topRight?: ReactNode;

  // Header image / text
  readonly imageSrc?: string;
  readonly imageAlt?: string;
  readonly imageFallback?: ReactNode;
  readonly badgeText?: string;

  // Content
  readonly title?: string;
  readonly description?: string;
  readonly badges?: ReadonlyArray<ReactNode>;

  // Card interaction
  readonly onClick?: () => void;
  readonly className?: string;
}

interface CardTableProps extends CardBaseProps {
  readonly table: ReadonlyArray<CardStat>;

  readonly metadata?: never;
  readonly actionLabel?: never;
  readonly onActionClick?: never;
  readonly actionDisabled?: never;
  readonly actionAriaLabel?: never;
}

interface CardActionProps extends CardBaseProps {
  readonly table?: never;

  readonly metadata?: ReactNode;
  readonly actionLabel?: string;
  readonly onActionClick?: () => void;
  readonly actionDisabled?: boolean;
  readonly actionAriaLabel?: string;
}

export type CardDetailEntidadProps =
  | CardTableProps
  | CardActionProps;

/* =========================================================
   Component
========================================================= */

export function CardDetailEntidad(props: CardDetailEntidadProps) {
  const {
    titleCab,
    subTitleCab,
    topRight,

    imageSrc,
    imageAlt = '',
    imageFallback,
    badgeText,

    title,
    description,
    badges = [],

    onClick,
    className = '',
  } = props;

  const isClickable = Boolean(onClick);

  const hasHeaderVisual =
    Boolean(imageSrc) ||
    imageFallback != null ||
    Boolean(badgeText);

  const hasHeader =
    hasHeaderVisual ||
    Boolean(titleCab) ||
    Boolean(subTitleCab) ||
    topRight != null;

  const hasTable = props.table !== undefined;

  const hasFooter =
    hasTable ||
    (!hasTable &&
      (props.metadata != null || Boolean(props.actionLabel)));

  /* =========================================================
     Header visual
  ========================================================= */

  const headerVisual = hasHeaderVisual ? (
    <div
      className="
        flex h-[34px] w-[34px] shrink-0
        items-center justify-center
        overflow-hidden rounded-md
        border-[0.8px] border-[#FF682C]
        text-sm font-medium
      "
    >
      {imageSrc ? (
        <img
          src={imageSrc}
          alt={imageAlt}
          className="h-full w-full object-cover"
        />
      ) : (
        imageFallback ?? badgeText
      )}
    </div>
  ) : null;

  /* =========================================================
     Render
  ========================================================= */

  return (
    <div
      className={`
        group relative flex h-full flex-col
        rounded-md bg-surface-ash p-5
        text-left
        dark:bg-btCard-dark
        ${isClickable ? 'cursor-pointer' : ''}
        ${className}
      `}
    >
      {/* Clickable surface covering the entire card */}
      {isClickable && (
        <button
          type="button"
          onClick={onClick}
          aria-label={`Open ${titleCab || title || 'card'}`}
          className="
            absolute inset-0 z-0
            h-full w-full rounded-md
            cursor-pointer
            absolute inset-0 z-0
            h-full w-full rounded-md
            cursor-pointer
            shadow-none
      hover:shadow-none
      focus:shadow-none
      active:shadow-none
      outline-none
            outline-none
            focus:outline-none
            focus-visible:outline-none
          "
        />
      )}

      {/* ================= HEADER ================= */}

      {hasHeader && (
        <div
          className="
            pointer-events-none relative z-0
            mb-3 flex items-start justify-between gap-3
          "
        >
          <div className="flex min-w-0 items-center gap-3">
            {headerVisual}

            {(titleCab || subTitleCab) && (
              <div className="min-w-0 text-[18px] leading-tight">
                {titleCab && (
                  <span className="block text-ink dark:text-ink-dark">
                    {titleCab}
                  </span>
                )}

                {subTitleCab && (
                  <span
                    className="
                      block text-[12.5px]
                      text-fg-secondary
                      dark:text-fg-secondary-dark
                    "
                  >
                    {subTitleCab}
                  </span>
                )}
              </div>
            )}
          </div>

          {topRight != null && (
            <div className="min-w-0">
              {topRight}
            </div>
          )}
        </div>
      )}

      {/* ================= CONTENT ================= */}

      <div className="pointer-events-none relative z-0">
        {title && (
          <h3
            className="
              mb-1 font-display text-lg font-normal
              tracking-[-0.02em]
              text-ink dark:text-ink-dark
            "
          >
            {title}
          </h3>
        )}

        {description && (
          <p
            className="
              mb-4 whitespace-pre-line
              text-[13.5px] leading-[1.45]
              text-fg-secondary
              dark:text-fg-secondary-dark
            "
          >
            {description}
          </p>
        )}

        {badges.length > 0 && (
          <div className="mb-4 flex flex-wrap gap-2">
            {badges.map((badge, index) => (
              <span key={index}>
                {badge}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* ================= FOOTER ================= */}

      {hasFooter && (
        <div
          className="
            pointer-events-none relative z-0
            mt-auto border-t border-[#e0ddd6]
            dark:border-line-dark
          "
        >
          {/* TABLE FOOTER */}

          {props.table !== undefined ? (
            <div className="overflow-x-auto pt-2">
              <table className="table-fixed text-center leading-none">
                <thead>
                  <tr>
                    {props.table.map((column, index) => (
                      <th
                        key={`label-${index}`}
                        className={`
                          px-2 py-0 text-[8px] font-medium
                          uppercase tracking-[0.04em]
                          text-fg-tertiary
                          dark:text-fg-tertiary-dark
                          ${
                            index < props.table.length - 1
                              ? 'border-r border-[#e0ddd6] dark:border-line-dark'
                              : ''
                          }
                        `}
                      >
                        {column.label}
                      </th>
                    ))}
                  </tr>
                </thead>

                <tbody>
                  <tr>
                    {props.table.map((column, index) => (
                      <td
                        key={`value-${index}`}
                        className={`
                          px-2 py-0 text-sm font-semibold
                          text-ink dark:text-ink-dark
                          ${
                            index < props.table.length - 1
                              ? 'border-r border-[#e0ddd6] dark:border-line-dark'
                              : ''
                          }
                        `}
                      >
                        {column.value}
                      </td>
                    ))}
                  </tr>
                </tbody>
              </table>
            </div>
          ) : (
            /* METADATA + ACTION FOOTER */

            <div
              className="
                flex items-center gap-3 pt-3
                text-xs text-fg-tertiary
                dark:text-fg-tertiary-dark
              "
            >
              {props.metadata != null && (
                <div className="min-w-0 flex-1">
                  {props.metadata}
                </div>
              )}

              {props.actionLabel && (
                <div className="pointer-events-auto relative z-10 shrink-0">
                  <ButtonApp
                    label={props.actionLabel}
                    variant="primary"
                    size="compact"
                    type="button"
                    onClick={props.onActionClick}
                    disabled={props.actionDisabled}
                  />
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default CardDetailEntidad;
