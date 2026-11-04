import { AlertTriangle, XCircle } from 'lucide-react';
import type { LifecycleStatus } from '../../types/services';
import { SERVICE_LIFECYCLE_STRINGS, formatEndOfServiceDate } from '../../utils/serviceLifecycle';

interface ServiceStatusBadgeProps {
  needsApiKey?: boolean;
  /** Last provider failure that needs action on the service (rejected key, quota). */
  lastError?: string | null;
  lastErrorAt?: string | null;
  /** Server-computed lifecycle status (never recomputed in the browser). */
  lifecycleStatus?: LifecycleStatus;
  endOfServiceAt?: string | null;
  deprecationNotice?: string | null;
}

/**
 * Status of an AI / embedding / sandbox service.
 * Precedence: retired > API key required > failing > deprecated > ready.
 */
function ServiceStatusBadge({
  needsApiKey,
  lastError,
  lastErrorAt,
  lifecycleStatus,
  endOfServiceAt,
  deprecationNotice,
}: Readonly<ServiceStatusBadgeProps>) {
  const date = endOfServiceAt ? formatEndOfServiceDate(endOfServiceAt) : '';
  const notice = deprecationNotice ? (
    <p className="mt-1 text-xs text-gray-600 dark:text-gray-300 whitespace-normal">{deprecationNotice}</p>
  ) : null;

  if (lifecycleStatus === 'retired') {
    const label = SERVICE_LIFECYCLE_STRINGS.retired;
    return (
      <div className="max-w-xs">
        <span
          className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-200"
        >
          <XCircle className="w-3 h-3" aria-hidden="true" /> {label}
        </span>
        {date && (
          <p className="mt-1 text-xs text-red-700 dark:text-red-300">
            {SERVICE_LIFECYCLE_STRINGS.retiredOn(date)}
          </p>
        )}
        {notice}
      </div>
    );
  }
  if (needsApiKey) {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-yellow-100 text-yellow-800 dark:bg-yellow-900/40 dark:text-yellow-200">
        <AlertTriangle className="w-3 h-3" aria-hidden="true" /> API Key Required
      </span>
    );
  }
  if (lastError) {
    return (
      <div className="max-w-xs">
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-200">
          <XCircle className="w-3 h-3" aria-hidden="true" /> Failing<span className="sr-only">:</span>
        </span>
        <p className="mt-1 text-xs text-red-700 dark:text-red-300 whitespace-normal">
          {lastError}
          {lastErrorAt && (
            <> Since <time dateTime={lastErrorAt}>{new Date(lastErrorAt).toLocaleString()}</time>.</>
          )}
        </p>
      </div>
    );
  }
  if (lifecycleStatus === 'deprecated') {
    const label = date
      ? SERVICE_LIFECYCLE_STRINGS.deprecated(date)
      : SERVICE_LIFECYCLE_STRINGS.deprecatedNoDate;
    return (
      <div className="max-w-xs">
        <span
          className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-orange-100 text-orange-800 dark:bg-orange-900/40 dark:text-orange-200"
        >
          <AlertTriangle className="w-3 h-3" aria-hidden="true" /> {label}
        </span>
        {notice}
      </div>
    );
  }
  return (
    <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-200">
      Ready
    </span>
  );
}

export default ServiceStatusBadge;
