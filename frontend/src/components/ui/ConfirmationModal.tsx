import { type ReactNode } from 'react';
import { AlertTriangle, AlertCircle, Info } from 'lucide-react';
import Modal from './Modal';

export type ConfirmVariant = 'danger' | 'warning' | 'info';

interface ConfirmationModalProps {
  readonly isOpen: boolean;
  readonly title: string;
  readonly message: ReactNode;
  readonly confirmLabel?: string;
  readonly cancelLabel?: string;
  readonly variant?: ConfirmVariant;
  readonly isLoading?: boolean;
  readonly onConfirm: () => void;
  readonly onCancel: () => void;
}

const variantStyles: Record<
  ConfirmVariant,
  { icon: ReactNode; iconBg: string; button: string }
> = {
  // Design v3 action language: red only for destructive, graphite for everything else.
  danger: {
    icon: <AlertTriangle className="w-6 h-6 text-error dark:text-error-dark" />,
    iconBg: 'bg-error-bg dark:bg-error-bg-dark',
    button: 'bg-error text-white hover:bg-error-strong focus-visible:ring-error dark:bg-error-dark dark:text-ink-on-dark dark:hover:bg-error-strong-dark',
  },
  warning: {
    icon: <AlertCircle className="w-6 h-6 text-bronze dark:text-bronze-dark" />,
    iconBg: 'bg-bronze-bg dark:bg-bronze-bg-dark',
    button: 'bg-ink text-ink-on hover:bg-ink/85 focus-visible:ring-focus dark:bg-ink-dark dark:text-ink-on-dark dark:hover:bg-ink-dark/85',
  },
  info: {
    icon: <Info className="w-6 h-6 text-info dark:text-info-dark" />,
    iconBg: 'bg-info-bg dark:bg-info-bg-dark',
    button: 'bg-ink text-ink-on hover:bg-ink/85 focus-visible:ring-focus dark:bg-ink-dark dark:text-ink-on-dark dark:hover:bg-ink-dark/85',
  },
};

function ConfirmationModal({
  isOpen,
  title,
  message,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  variant = 'danger',
  isLoading = false,
  onConfirm,
  onCancel,
}: ConfirmationModalProps) {
  const styles = variantStyles[variant];

  return (
    <Modal isOpen={isOpen} onClose={isLoading ? () => {} : onCancel} title={title} size="small">
      <div className="flex gap-4">
        <div
          className={`flex-shrink-0 w-12 h-12 rounded-lg flex items-center justify-center ${styles.iconBg}`}
        >
          {styles.icon}
        </div>
        <div className="flex-1 text-sm text-fg-secondary dark:text-fg-secondary-dark pt-2">{message}</div>
      </div>
      <div className="mt-6 flex justify-end gap-3">
        <button
          type="button"
          onClick={onCancel}
          disabled={isLoading}
          className="px-4 py-2 text-sm font-medium text-fg bg-transparent border border-line-strong rounded-lg hover:bg-surface-hover focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-focus disabled:opacity-50 dark:text-fg-dark dark:border-line-strong-dark dark:hover:bg-surface-hover-dark dark:focus-visible:ring-focus-dark dark:focus-visible:ring-offset-surface-dark"
        >
          {cancelLabel}
        </button>
        <button
          type="button"
          onClick={onConfirm}
          disabled={isLoading}
          className={`inline-flex items-center px-4 py-2 text-sm font-medium rounded-lg focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 dark:focus-visible:ring-offset-surface-dark disabled:opacity-50 ${styles.button}`}
        >
          {isLoading && (
            <svg
              className="animate-spin -ml-1 mr-2 h-4 w-4 text-current"
              fill="none"
              viewBox="0 0 24 24"
              aria-hidden="true"
            >
              <circle
                className="opacity-25"
                cx="12"
                cy="12"
                r="10"
                stroke="currentColor"
                strokeWidth="4"
              />
              <path
                className="opacity-75"
                fill="currentColor"
                d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z"
              />
            </svg>
          )}
          {confirmLabel}
        </button>
      </div>
    </Modal>
  );
}

export default ConfirmationModal;
