import { AlertTriangle, XCircle } from 'lucide-react';
import Alert from '../ui/Alert';
import type { ServiceLifecycleWarning } from '../../types/services';
import {
  SERVICE_LIFECYCLE_STRINGS,
  SERVICE_WARNING_STRINGS,
  formatEndOfServiceDate,
} from '../../utils/serviceLifecycle';

export interface ServiceLifecycleAlertProps {
  readonly warnings?: readonly ServiceLifecycleWarning[] | null;
  readonly variant: 'compact' | 'full';
  readonly className?: string;
}

function roleLabel(w: ServiceLifecycleWarning): string {
  const s = SERVICE_WARNING_STRINGS;
  if (w.role === 'silo_embedding') return s.silo_embedding(w.via ?? '');
  if (w.role === 'middleware') return s.middleware(w.via ?? '');
  if (w.role === 'sandbox' && w.via === 'app default') return s.roles.sandbox_app_default;
  return s.roles[w.role];
}

function statusText(w: ServiceLifecycleWarning): string {
  const date = formatEndOfServiceDate(w.end_of_service_at);
  return w.lifecycle_status === 'retired'
    ? SERVICE_WARNING_STRINGS.retiredStatus(date)
    : SERVICE_WARNING_STRINGS.deprecatedStatus(date);
}

function hintText(w: ServiceLifecycleWarning): string | null {
  const date = formatEndOfServiceDate(w.end_of_service_at);
  if (w.kind === 'embedding') return SERVICE_LIFECYCLE_STRINGS.embeddingWarning(date);
  if (w.kind === 'sandbox') return SERVICE_WARNING_STRINGS.sandboxWarning(date);
  return null;
}

/**
 * Lists deprecated / retired services used by a resource. Notices are rendered as
 * plain text (React escapes them) — never markdown or HTML.
 */
function ServiceLifecycleAlert({ warnings, variant, className = '' }: ServiceLifecycleAlertProps) {
  if (!warnings || warnings.length === 0) return null;
  const retired = warnings.filter((w) => w.lifecycle_status === 'retired');
  const hasRetired = retired.length > 0;

  if (variant === 'compact') {
    const count = hasRetired ? retired.length : warnings.length;
    const label = hasRetired
      ? SERVICE_WARNING_STRINGS.compactRetired(count)
      : SERVICE_WARNING_STRINGS.compactDeprecated(count);
    const details = warnings
      .map((w) => `${w.service_name}, ${roleLabel(w)}, ${statusText(w)}`)
      .join('; ');
    const tone = hasRetired
      ? 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-200'
      : 'bg-orange-100 text-orange-800 dark:bg-orange-900/40 dark:text-orange-200';
    const Icon = hasRetired ? XCircle : AlertTriangle;
    return (
      <span
        className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${tone} ${className}`}
      >
        <Icon className="w-3 h-3" aria-hidden="true" />
        <span aria-hidden="true">{label}</span>
        <span className="sr-only">{`. ${SERVICE_WARNING_STRINGS.compactAria(details)}`}</span>
      </span>
    );
  }

  const ordered = [...retired, ...warnings.filter((w) => w.lifecycle_status !== 'retired')];
  return (
    <Alert
      type={hasRetired ? 'error' : 'warning'}
      polite
      className={className}
      title={hasRetired ? SERVICE_WARNING_STRINGS.titleRetired : SERVICE_WARNING_STRINGS.titleDeprecated}
      message={
        <div className="whitespace-normal">
          <ul className="list-disc pl-5 space-y-1">
            {ordered.map((w) => {
              const hint = hintText(w);
              return (
                <li key={`${w.service_id}-${w.kind}-${w.role}-${w.via ?? ''}`}>
                  <span className="font-medium">{w.service_name}</span>
                  <span aria-hidden="true"> · </span>
                  {roleLabel(w)}
                  <span aria-hidden="true"> · </span>
                  {statusText(w)}
                  {w.deprecation_notice && <span className="block">{w.deprecation_notice}</span>}
                  {hint && <span className="block">{hint}</span>}
                </li>
              );
            })}
          </ul>
        </div>
      }
    />
  );
}

export default ServiceLifecycleAlert;
