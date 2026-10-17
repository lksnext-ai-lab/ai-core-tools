import { AlertTriangle, XCircle } from 'lucide-react';

interface ServiceStatusBadgeProps {
  needsApiKey?: boolean;
  /** Last provider failure that needs action on the service (rejected key, quota). */
  lastError?: string | null;
  lastErrorAt?: string | null;
}

/** Status of an AI / embedding service: missing key, failing (with the reason), or ready. */
function ServiceStatusBadge({ needsApiKey, lastError, lastErrorAt }: Readonly<ServiceStatusBadgeProps>) {
  if (needsApiKey) {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-yellow-100 text-yellow-800">
        <AlertTriangle className="w-3 h-3" aria-hidden="true" /> API Key Required
      </span>
    );
  }
  if (lastError) {
    return (
      <div className="max-w-xs">
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-800">
          <XCircle className="w-3 h-3" aria-hidden="true" /> Failing<span className="sr-only">:</span>
        </span>
        <p className="mt-1 text-xs text-red-700 whitespace-normal">
          {lastError}
          {lastErrorAt && (
            <> Since <time dateTime={lastErrorAt}>{new Date(lastErrorAt).toLocaleString()}</time>.</>
          )}
        </p>
      </div>
    );
  }
  return (
    <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
      Ready
    </span>
  );
}

export default ServiceStatusBadge;
