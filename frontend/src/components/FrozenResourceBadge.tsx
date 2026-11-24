import React from 'react';
import { useTranslation } from 'react-i18next';

interface FrozenResourceBadgeProps {
  /** Whether the resource is currently frozen */
  isFrozen: boolean;
  /** Optional class names applied to the wrapper */
  className?: string;
}

/**
 * Lock icon + muted overlay rendered over list items and detail views
 * when a resource is frozen due to a tier downgrade.
 *
 * Usage:
 *   <FrozenResourceBadge isFrozen={agent.is_frozen} />
 */
const FrozenResourceBadge: React.FC<FrozenResourceBadgeProps> = ({ isFrozen, className = '' }) => {
  const { t } = useTranslation('common');

  if (!isFrozen) return null;

  return (
    <span
      className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-xs font-medium bg-tableCab dark:bg-tableCab-dark text-fg-tertiary dark:text-fg-tertiary-dark border border-line dark:border-line-dark ${className}`}
      title={t('frozenResourceBadge.tooltip')}
    >
      {/* Lock icon (heroicons outline) */}
      <svg
        xmlns="http://www.w3.org/2000/svg"
        className="h-3 w-3"
        fill="none"
        viewBox="0 0 24 24"
        stroke="currentColor"
        strokeWidth={2}
        aria-hidden="true"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"
        />
      </svg>
      {t('frozenResourceBadge.label')}
    </span>
  );
};

export default FrozenResourceBadge;
