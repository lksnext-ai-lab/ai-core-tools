
import React, { type ReactNode } from 'react';
import { CheckCircle2, AlertTriangle, Info } from 'lucide-react';

interface AlertProps {
  type: 'success' | 'error' | 'warning' | 'info';
  title?: string;
  message: string | ReactNode;
  onDismiss?: () => void;
  className?: string;
  /** Announce politely (role=status) even for error/warning types. Default: false. */
  polite?: boolean;
}

const alertStyles = {
  success: {
    container: 'bg-green-50 border-green-200 dark:bg-green-900/30 dark:border-green-800',
    iconColor: 'text-green-400 dark:text-green-300',
    titleColor: 'text-green-800 dark:text-green-200',
    messageColor: 'text-green-600 dark:text-green-200',
    buttonColor: 'text-green-600 hover:text-green-800 dark:text-green-300 dark:hover:text-green-100',
  },
  error: {
    container: 'bg-red-50 border-red-200 dark:bg-red-900/30 dark:border-red-800',
    iconColor: 'text-red-400 dark:text-red-300',
    titleColor: 'text-red-800 dark:text-red-200',
    messageColor: 'text-red-700 dark:text-red-200',
    buttonColor: 'text-red-600 hover:text-red-800 dark:text-red-300 dark:hover:text-red-100',
  },
  warning: {
    container: 'bg-yellow-50 border-yellow-200 dark:bg-yellow-900/30 dark:border-yellow-800',
    iconColor: 'text-yellow-400 dark:text-yellow-300',
    titleColor: 'text-yellow-800 dark:text-yellow-200',
    messageColor: 'text-yellow-800 dark:text-yellow-200',
    buttonColor: 'text-yellow-600 hover:text-yellow-800 dark:text-yellow-300 dark:hover:text-yellow-100',
  },
  info: {
    container: 'bg-blue-50 border-blue-200 dark:bg-blue-900/30 dark:border-blue-800',
    iconColor: 'text-blue-400 dark:text-blue-300',
    titleColor: 'text-blue-800 dark:text-blue-200',
    messageColor: 'text-blue-600 dark:text-blue-200',
    buttonColor: 'text-blue-600 hover:text-blue-800 dark:text-blue-300 dark:hover:text-blue-100',
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
  className = '',
  polite = false
}) => {
  const styles = alertStyles[type];
  const defaultTitle = type.charAt(0).toUpperCase() + type.slice(1);
  const assertive = !polite && (type === 'error' || type === 'warning');

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
          <div className={`text-sm ${styles.messageColor} mt-1 whitespace-pre-line`}>{message}</div>
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
