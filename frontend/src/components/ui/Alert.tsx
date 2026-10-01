
import React, { type ReactNode } from 'react';
import { CheckCircle2, AlertTriangle, Info } from 'lucide-react';

interface AlertProps {
  type: 'success' | 'error' | 'warning' | 'info';
  title?: string;
  message: string | ReactNode;
  onDismiss?: () => void;
  className?: string;
}

const alertStyles = {
  success: {
    container: 'bg-success-bg border-success-border dark:bg-success-bg-dark dark:border-success-border-dark',
    iconColor: 'text-success dark:text-success-dark',
    titleColor: 'text-success-strong dark:text-success-strong-dark',
    messageColor: 'text-success dark:text-success-dark',
    buttonColor: 'text-success hover:text-success-strong dark:text-success-dark dark:hover:text-success-strong-dark',
  },
  error: {
    container: 'bg-error-bg border-error-border dark:bg-error-bg-dark dark:border-error-border-dark',
    iconColor: 'text-error dark:text-error-dark',
    titleColor: 'text-error-strong dark:text-error-strong-dark',
    messageColor: 'text-error dark:text-error-dark',
    buttonColor: 'text-error hover:text-error-strong dark:text-error-dark dark:hover:text-error-strong-dark',
  },
  warning: {
    container: 'bg-bronze-bg border-bronze-border dark:bg-bronze-bg-dark dark:border-bronze-border-dark',
    iconColor: 'text-bronze dark:text-bronze-dark',
    titleColor: 'text-bronze-strong dark:text-bronze-strong-dark',
    messageColor: 'text-bronze dark:text-bronze-dark',
    buttonColor: 'text-bronze hover:text-bronze-strong dark:text-bronze-dark dark:hover:text-bronze-strong-dark',
  },
  info: {
    container: 'bg-info-bg border-info-border dark:bg-info-bg-dark dark:border-info-border-dark',
    iconColor: 'text-info dark:text-info-dark',
    titleColor: 'text-info dark:text-info-dark',
    messageColor: 'text-fg-secondary dark:text-fg-secondary-dark',
    buttonColor: 'text-info hover:text-info-strong dark:text-info-dark dark:hover:text-info-strong-dark',
  },
};

const alertIcons = {
  success: <CheckCircle2 className="w-5 h-5" />,
  error: <AlertTriangle className="w-5 h-5" />,
  warning: <AlertTriangle className="w-5 h-5" />,
  info: <Info className="w-5 h-5" />,
};

const Alert: React.FC<AlertProps> = ({
  type,
  title,
  message,
  onDismiss,
  className = ''
}) => {
  const styles = alertStyles[type];
  const defaultTitle = type.charAt(0).toUpperCase() + type.slice(1);
  const assertive = type === 'error' || type === 'warning';

  return (
    <div
      className={`${styles.container} border rounded-lg p-4 ${className}`}
      role={assertive ? 'alert' : 'status'}
      aria-live={assertive ? 'assertive' : 'polite'}
    >
      <div className="flex">
        <span className={`${styles.iconColor} mr-3 shrink-0`} aria-hidden="true">{alertIcons[type]}</span>
        <div className="flex-1">
          <h3 className={`text-sm font-medium ${styles.titleColor}`}>
            {title || defaultTitle}
          </h3>
          <p className={`text-sm ${styles.messageColor} mt-1`}>{message}</p>
          {onDismiss && (
            <button
              type="button"
              onClick={onDismiss}
              className={`mt-2 text-sm ${styles.buttonColor} underline`}
            >
              Dismiss
            </button>
          )}
        </div>
      </div>
    </div>
  );
};

export default Alert;
