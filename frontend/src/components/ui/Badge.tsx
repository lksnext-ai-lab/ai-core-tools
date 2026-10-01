import React from 'react';
import { Check, X, AlertTriangle } from 'lucide-react';

type BadgeVariant = 'success' | 'info' | 'warning' | 'error' | 'default' | 'primary' | 'secondary';

interface BadgeProps {
  readonly label: string;
  readonly variant?: BadgeVariant;
  readonly className?: string;
  readonly icon?: React.ReactNode;
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
    success: 'bg-success-bg text-success dark:bg-success-bg-dark dark:text-success-dark',
    info: 'bg-info-bg text-info dark:bg-info-bg-dark dark:text-info-dark',
    warning: 'bg-bronze-bg text-bronze dark:bg-bronze-bg-dark dark:text-bronze-dark',
    error: 'bg-error-bg text-error dark:bg-error-bg-dark dark:text-error-dark',
    default: 'bg-surface-hover text-fg-secondary dark:bg-surface-hover-dark dark:text-fg-secondary-dark',
    primary: 'bg-ink text-ink-on dark:bg-ink-dark dark:text-ink-on-dark',
    secondary: 'bg-bronze-bg-soft text-bronze-strong dark:bg-bronze-bg-soft-dark dark:text-bronze-strong-dark'
  };

  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-[11px] font-medium ${variantClasses[variant]} ${className}`}>
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
    // Provider palette from the v3 design (OpenAI=success, Azure=info, Anthropic=bronze, Mistral=error, rest neutral)
    'openai': 'bg-success-bg text-success dark:bg-success-bg-dark dark:text-success-dark',
    'OpenAI': 'bg-success-bg text-success dark:bg-success-bg-dark dark:text-success-dark',
    'azure': 'bg-info-bg text-info dark:bg-info-bg-dark dark:text-info-dark',
    'Azure': 'bg-info-bg text-info dark:bg-info-bg-dark dark:text-info-dark',
    'mistralai': 'bg-error-bg text-error dark:bg-error-bg-dark dark:text-error-dark',
    'MistralAI': 'bg-error-bg text-error dark:bg-error-bg-dark dark:text-error-dark',
    'ollama': 'bg-bronze-bg-soft text-bronze-strong dark:bg-bronze-bg-soft-dark dark:text-bronze-strong-dark',
    'Ollama': 'bg-bronze-bg-soft text-bronze-strong dark:bg-bronze-bg-soft-dark dark:text-bronze-strong-dark',
    'custom': 'bg-surface-hover text-fg-secondary dark:bg-surface-hover-dark dark:text-fg-secondary-dark',
    'Custom': 'bg-surface-hover text-fg-secondary dark:bg-surface-hover-dark dark:text-fg-secondary-dark',
    'anthropic': 'bg-bronze-bg text-bronze dark:bg-bronze-bg-dark dark:text-bronze-dark',
    'Anthropic': 'bg-bronze-bg text-bronze dark:bg-bronze-bg-dark dark:text-bronze-dark',
    'google': 'bg-info-bg text-info-strong dark:bg-info-bg-dark dark:text-info-strong-dark',
    'Google': 'bg-info-bg text-info-strong dark:bg-info-bg-dark dark:text-info-strong-dark',
  };

  const colorClass = providerColors[provider] || 'bg-surface-hover text-fg-secondary dark:bg-surface-hover-dark dark:text-fg-secondary-dark';

  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-[11px] font-medium ${colorClass} ${className}`}>
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
  const statusConfig: Record<StatusType, { label: string; color: string; icon?: React.ReactNode }> = {
    active: { label: 'Active', color: 'bg-success-bg text-success dark:bg-success-bg-dark dark:text-success-dark', icon: <span className="w-1.5 h-1.5 rounded-full bg-success dark:bg-success-dark inline-block" /> },
    inactive: { label: 'Inactive', color: 'bg-surface-hover text-fg-tertiary dark:bg-surface-hover-dark dark:text-fg-tertiary-dark', icon: <span className="w-1.5 h-1.5 rounded-full bg-fg-faint2 dark:bg-fg-faint2-dark inline-block" /> },
    pending: { label: 'Pending', color: 'bg-bronze-bg text-bronze dark:bg-bronze-bg-dark dark:text-bronze-dark', icon: <span className="w-1.5 h-1.5 rounded-full bg-bronze dark:bg-bronze-dark inline-block" /> },
    error: { label: 'Error', color: 'bg-error-bg text-error dark:bg-error-bg-dark dark:text-error-dark', icon: <X className="w-3 h-3" /> },
    success: { label: 'Success', color: 'bg-success-bg text-success dark:bg-success-bg-dark dark:text-success-dark', icon: <Check className="w-3 h-3" /> },
    warning: { label: 'Warning', color: 'bg-bronze-bg text-bronze dark:bg-bronze-bg-dark dark:text-bronze-dark', icon: <AlertTriangle className="w-3 h-3" /> }
  };

  const config = statusConfig[status];
  const label = customLabel || config.label;

  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-[11px] font-medium ${config.color} ${className}`}>
      {config.icon && <span className="mr-1">{config.icon}</span>}
      {label}
    </span>
  );
}

export default Badge;

