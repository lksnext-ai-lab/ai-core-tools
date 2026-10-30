import React from 'react';
import { Check, Pencil, Trash2, X } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

export type ButtonTabItemVariant = 'edit' | 'link';

export interface ButtonTabItemProps {
  readonly title: string;
  readonly description?: string;
  readonly dateTime?: string;
  readonly dateLabel?: string;
  readonly icon?: React.ReactNode;
  readonly variant?: ButtonTabItemVariant;
  readonly isEditing?: boolean;
  readonly editingTitle?: string;
  readonly to?: string;
  readonly onClick?: () => void;
  readonly onEdit?: () => void;
  readonly onDelete?: () => void;
  readonly onTitleChange?: (value: string) => void;
  readonly onSaveTitle?: () => void;
  readonly onCancelEdit?: () => void;
}

/** Row for a ButtonTab list: icon, title, date and description, with inline rename/delete ('edit') or an Open link ('link'). */
export function ButtonTabItem({
  title,
  description,
  dateTime,
  dateLabel,
  icon,
  variant = 'edit',
  isEditing = false,
  editingTitle = title,
  to,
  onClick,
  onEdit,
  onDelete,
  onTitleChange,
  onSaveTitle,
  onCancelEdit,
}: ButtonTabItemProps) {
  const { t } = useTranslation('common');
  const cancelBlurRef = React.useRef(false);
  const canEdit = variant === 'edit';
  const isTitleEditing = canEdit && isEditing;

  function handleBlur() {
    if (cancelBlurRef.current) {
      cancelBlurRef.current = false;
      return;
    }
    onSaveTitle?.();
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'Enter') {
      event.preventDefault();
      event.currentTarget.blur();
    } else if (event.key === 'Escape') {
      event.preventDefault();
      cancelBlurRef.current = true;
      onCancelEdit?.();
    }
  }

  function handleContainerKeyDown(event: React.KeyboardEvent<HTMLDivElement>) {
    if (event.target !== event.currentTarget || !onClick) return;
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      onClick();
    }
  }

  return (
    <div
      role="listitem"
      tabIndex={onClick && !isTitleEditing ? 0 : undefined}
      onClick={isTitleEditing ? undefined : onClick}
      onKeyDown={handleContainerKeyDown}
      className={`group flex min-h-[65px] items-center gap-3 border-b border-line bg-surface px-[18px] py-[15px] transition-colors last:border-b-0 hover:bg-surface-hover dark:border-line-dark dark:bg-surface-dark dark:hover:bg-surface-hover-dark ${onClick && !isTitleEditing ? 'cursor-pointer' : ''}`}
    >
      <div className="flex h-[34px] w-[34px] shrink-0 items-center justify-center overflow-hidden">
        {icon}
      </div>

      {isTitleEditing ? (
        <div className="flex min-w-0 flex-1 items-center gap-2">
          <input
            autoFocus
            aria-label={t('marketplaceHome.conversationTitle')}
            type="text"
            value={editingTitle}
            onChange={(event) => onTitleChange?.(event.target.value)}
            onBlur={handleBlur}
            onKeyDown={handleKeyDown}
            className="min-w-0 flex-1 border-b border-bronze bg-transparent py-1 text-sm font-medium text-fg outline-none dark:text-fg-dark"
          />
          <button
            type="button"
            onMouseDown={(event) => event.preventDefault()}
            onClick={(event) => {
              event.stopPropagation();
              onSaveTitle?.();
            }}
            aria-label={t('marketplaceHome.saveConversationTitle')}
            title={t('marketplaceHome.saveTitle')}
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded text-fg-secondary hover:bg-bronze-border dark:text-fg-secondary-dark dark:hover:bg-surface-hover-dark"
          >
            <Check className="h-4 w-4" aria-hidden="true" />
          </button>
          <button
            type="button"
            onMouseDown={(event) => event.preventDefault()}
            onClick={(event) => {
              event.stopPropagation();
              cancelBlurRef.current = true;
              onCancelEdit?.();
            }}
            aria-label={t('marketplaceHome.cancelTitleEdit')}
            title={t('marketplaceHome.cancelTitleEdit')}
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded text-fg-secondary hover:bg-bronze-bg-soft dark:text-fg-secondary-dark dark:hover:bg-surface-hover-dark"
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>
      ) : (
        <div className="flex min-w-0 flex-1 items-center gap-3 text-left">
          <span className="min-w-0 flex-1">
            <span className="flex min-w-0 items-center gap-2">
              <span className="flex min-w-0 items-center gap-1">
                <span className="min-w-0 truncate text-sm font-medium text-fg dark:text-fg-dark">
                  {title}
                </span>
                {canEdit && onEdit && (
                  <button
                    type="button"
                    onClick={(event) => {
                      event.stopPropagation();
                      onEdit();
                    }}
                    aria-label={t('marketplaceHome.renameConversation')}
                    title={t('marketplaceHome.renameConversation')}
                    className="flex h-8 w-8 shrink-0 items-center justify-center  text-fg-tertiary dark:text-fg-tertiary-dark opacity-0 transition group-hover:opacity-100 focus:opacity-100  hover:text-fg-secondary  dark:hover:text-fg-tertiary-dark"
                  >
                    <Pencil className="h-3.5 w-3.5" aria-hidden="true" />
                  </button>
                )}
              </span>
              {canEdit && dateLabel && (
                <time
                  dateTime={dateTime}
                  className="ml-auto shrink-0 text-xs text-fg-secondary dark:text-fg-secondary-dark"
                >
                  {dateLabel}
                </time>
              )}
            </span>
            {description && (
              <span className="mt-0.5 block min-w-0 whitespace-pre-line line-clamp-2 text-xs text-fg-secondary dark:text-fg-secondary-dark">
                {description}
              </span>
            )}
          </span>
          {variant === 'link' && to && (
            <Link
              to={to}
              onClick={(event) => event.stopPropagation()}
              className="shrink-0 text-xs text-fg underline decoration-accent underline-offset-[3px] dark:text-fg-dark"
            >
              Open
            </Link>
          )}
        </div>
      )}

      {!isTitleEditing && (
        <div className="flex shrink-0 items-center gap-1">
          {canEdit && onDelete && (
            <button
              type="button"
              onClick={(event) => {
                event.stopPropagation();
                onDelete();
              }}
              aria-label={t('marketplaceHome.deleteConversation')}
              title={t('marketplaceHome.deleteConversation')}
              className="flex h-8 w-8 items-center justify-center  text-fg-tertiary dark:text-fg-tertiary-dark opacity-0 transition group-hover:opacity-100 focus:opacity-100 hover:text-fg-secondary  dark:hover:text-fg-tertiary-dark"
            >
              <Trash2 className="h-4 w-4" aria-hidden="true" />
            </button>
          )}
        </div>
      )}
    </div>
  );
}

export default ButtonTabItem;
