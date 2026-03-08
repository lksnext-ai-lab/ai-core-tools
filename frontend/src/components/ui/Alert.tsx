
 import React, { type ReactNode } from 'react';

interface AlertProps {
  type: 'success' | 'error' | 'warning' | 'info';
  title?: string;
  message: string | ReactNode;
  onDismiss?: () => void;
  className?: string;
}

const alertStyles = {
  success: {
    container: 'bg-green-50 border-green-200',
    icon: '✅',
    iconColor: 'text-green-400',
    titleColor: 'text-green-800',
    messageColor: 'text-green-600',
    buttonColor: 'text-green-600 hover:text-green-800',
  },
  error: {
    container: 'bg-red-50 border-red-200',
    icon: '⚠️',
    iconColor: 'text-red-400',
    titleColor: 'text-red-800',
    messageColor: 'text-red-600',
    buttonColor: 'text-red-600 hover:text-red-800',
  },
  warning: {
    container: 'bg-yellow-50 border-yellow-200',
    icon: '⚠️',
    iconColor: 'text-yellow-400',
    titleColor: 'text-yellow-800',
    messageColor: 'text-yellow-600',
    buttonColor: 'text-yellow-600 hover:text-yellow-800',
  },
  info: {
    container: 'bg-blue-50 border-blue-200',
    icon: 'ℹ️',
    iconColor: 'text-blue-400',
    titleColor: 'text-blue-800',
    messageColor: 'text-blue-600',
    buttonColor: 'text-blue-600 hover:text-blue-800',
  },
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

  return (
    <div className={`${styles.container} border rounded-lg p-4 ${className}`}>
      <div className="flex">
        <span className={`${styles.iconColor} text-xl mr-3`}>{styles.icon}</span>
        <div className="flex-1">
          <h3 className={`text-sm font-medium ${styles.titleColor}`}>
            {title || defaultTitle}
          </h3>
          <p className={`text-sm ${styles.messageColor} mt-1`}>{message}</p>
          {onDismiss && (
            <button 
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
