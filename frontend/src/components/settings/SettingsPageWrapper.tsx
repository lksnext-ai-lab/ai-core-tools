import React from 'react';
import { LoadingState } from '../ui/LoadingState';
import { ErrorState } from '../ui/ErrorState';

interface SettingsPageWrapperProps {
  readonly title: string;
  readonly description: string;
  readonly loading: boolean;
  readonly error: string | null;
  readonly onRetry: () => void;
  readonly onAdd?: () => void;
  readonly addButtonLabel?: string;
  readonly children: React.ReactNode;
  readonly className?: string;
  readonly headerClassName?: string;
  readonly showAddButton?: boolean;
}

/**
 * Reusable settings page wrapper component
 * Handles loading/error states and provides consistent page header
 */
export function SettingsPageWrapper({
  title,
  description,
  loading,
  error,
  onRetry,
  onAdd,
  addButtonLabel = 'Add',
  children,
  className = '',
  headerClassName = '',
  showAddButton = true
}: SettingsPageWrapperProps) {
  // Show loading state
  if (loading) {
    return <LoadingState message={`Loading ${title.toLowerCase()}...`} />;
  }

  // Show error state
  if (error) {
    return <ErrorState error={error} onRetry={onRetry} />;
  }

  // Show content
  return (
    <div className={`p-6 ${className}`}>
      {/* Header */}
      <div className={`flex justify-between items-center mb-6 ${headerClassName}`}>
        <div>
          <h2 className="text-xl font-semibold text-gray-900">{title}</h2>
          <p className="text-gray-600">{description}</p>
        </div>
        {showAddButton && onAdd && (
          <button 
            onClick={onAdd}
            className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg flex items-center transition-colors"
          >
            <span className="mr-2">+</span>
            {addButtonLabel}
          </button>
        )}
      </div>

      {/* Content */}
      {children}
    </div>
  );
}

export default SettingsPageWrapper;

