import React from 'react';

type BadgeVariant = 'success' | 'info' | 'warning' | 'error' | 'default' | 'primary' | 'secondary';

interface BadgeProps {
  readonly label: string;
  readonly variant?: BadgeVariant;
  readonly className?: string;
  readonly icon?: string;
}

/**
 * Reusable badge component with predefined color variants
 */
export function Badge({ 
  label, 
  variant = 'default',
  className = '',
  icon
}: BadgeProps) {
  const variantClasses: Record<BadgeVariant, string> = {
    success: 'bg-green-100 text-green-800',
    info: 'bg-blue-100 text-blue-800',
    warning: 'bg-yellow-100 text-yellow-800',
    error: 'bg-red-100 text-red-800',
    default: 'bg-gray-100 text-gray-800',
    primary: 'bg-indigo-100 text-indigo-800',
    secondary: 'bg-purple-100 text-purple-800'
  };

  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${variantClasses[variant]} ${className}`}>
      {icon && <span className="mr-1">{icon}</span>}
      {label}
    </span>
  );
}

interface ProviderBadgeProps {
  readonly provider: string;
  readonly className?: string;
}

/**
 * Badge component specifically for AI/Embedding service providers
 */
export function ProviderBadge({ provider, className = '' }: ProviderBadgeProps) {
  const providerColors: Record<string, string> = {
    'openai': 'bg-green-100 text-green-800',
    'OpenAI': 'bg-green-100 text-green-800',
    'azure': 'bg-blue-100 text-blue-800',
    'Azure': 'bg-blue-100 text-blue-800',
    'mistralai': 'bg-purple-100 text-purple-800',
    'MistralAI': 'bg-purple-100 text-purple-800',
    'ollama': 'bg-orange-100 text-orange-800',
    'Ollama': 'bg-orange-100 text-orange-800',
    'custom': 'bg-gray-100 text-gray-800',
    'Custom': 'bg-gray-100 text-gray-800',
    'anthropic': 'bg-red-100 text-red-800',
    'Anthropic': 'bg-red-100 text-red-800',
    'google': 'bg-yellow-100 text-yellow-800',
    'Google': 'bg-yellow-100 text-yellow-800',
  };

  const colorClass = providerColors[provider] || 'bg-gray-100 text-gray-800';

  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${colorClass} ${className}`}>
      {provider}
    </span>
  );
}

type StatusType = 'active' | 'inactive' | 'pending' | 'error' | 'success' | 'warning';

interface StatusBadgeProps {
  readonly status: StatusType;
  readonly className?: string;
  readonly customLabel?: string;
}

/**
 * Badge component for status indicators
 */
export function StatusBadge({ status, className = '', customLabel }: StatusBadgeProps) {
  const statusConfig: Record<StatusType, { label: string; color: string; icon?: string }> = {
    active: { label: 'Active', color: 'bg-green-100 text-green-800', icon: '●' },
    inactive: { label: 'Inactive', color: 'bg-gray-100 text-gray-800', icon: '○' },
    pending: { label: 'Pending', color: 'bg-yellow-100 text-yellow-800', icon: '◐' },
    error: { label: 'Error', color: 'bg-red-100 text-red-800', icon: '✕' },
    success: { label: 'Success', color: 'bg-green-100 text-green-800', icon: '✓' },
    warning: { label: 'Warning', color: 'bg-orange-100 text-orange-800', icon: '⚠' }
  };

  const config = statusConfig[status];
  const label = customLabel || config.label;

  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${config.color} ${className}`}>
      {config.icon && <span className="mr-1">{config.icon}</span>}
      {label}
    </span>
  );
}

export default Badge;

