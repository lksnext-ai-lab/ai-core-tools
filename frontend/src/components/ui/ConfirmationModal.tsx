import { type ReactNode } from 'react';
import { AlertTriangle, AlertCircle, Info } from 'lucide-react';
import Modal from './Modal';
import ButtonApp, { type ButtonAppVariant } from './ButtonApp';

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
  { icon: ReactNode; iconBg: string; button: ButtonAppVariant }
> = {
  // Design v3 action language: red only for destructive, graphite for everything else.
  danger: {
    icon: <AlertTriangle className="w-6 h-6 text-error dark:text-error-dark" />,
    iconBg: 'bg-error-bg dark:bg-error-bg-dark',
    button: 'dangerSolid',
  },
  warning: {
    icon: <AlertCircle className="w-6 h-6 text-bronze dark:text-bronze-dark" />,
    iconBg: 'bg-bronze-bg dark:bg-bronze-bg-dark',
    button: 'primary',
  },
  info: {
    icon: <Info className="w-6 h-6 text-info dark:text-info-dark" />,
    iconBg: 'bg-info-bg dark:bg-info-bg-dark',
    button: 'primary',
  },
};

/** Confirmation dialog used by the global confirm() (ConfirmContext). Red solid action only for 'danger'. */
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
        <ButtonApp
          label={cancelLabel}
          onClick={onCancel}
          disabled={isLoading}
          variant="secondary"
          size="medium"
        />
        <ButtonApp
          label={confirmLabel}
          onClick={onConfirm}
          loading={isLoading}
          variant={styles.button}
          size="medium"
        />
      </div>
    </Modal>
  );
}

export default ConfirmationModal;
