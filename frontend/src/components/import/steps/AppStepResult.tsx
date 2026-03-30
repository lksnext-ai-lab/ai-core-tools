import Alert from '../../ui/Alert';
import type { FullAppImportResponse } from '../../../types/import';

interface Props {
  result: FullAppImportResponse | null;
  isImporting: boolean;
  importError: string | null;
  onClose: () => void;
  onOpenApp: () => void;
  onRetry: () => void;
}

function AppStepResult({
  result,
  isImporting,
  importError,
  onClose,
  onOpenApp,
  onRetry,
}: Readonly<Props>) {
  if (isImporting) {
    return (
      <div className="flex flex-col items-center justify-center py-12 space-y-4">
        <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-blue-600" />
        <p className="text-sm text-gray-600">
          Importing app...
        </p>
      </div>
    );
  }

  if (importError) {
    return (
      <div className="space-y-4">
        <Alert type="error" message={importError} />
        <div className="flex justify-center space-x-3">
          <button
            type="button"
            onClick={onRetry}
            className="px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700"
          >
            Try Again
          </button>
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 text-sm bg-white text-gray-700 border border-gray-300 rounded-lg hover:bg-gray-50"
          >
            Close
          </button>
        </div>
      </div>
    );
  }

  if (!result) return null;

  if (result.success && result.summary) {
    const s = result.summary;
    return (
      <div className="space-y-4">
        <Alert
          type="success"
          title="Import Successful"
          message={result.message}
        />

        <div className="bg-gray-50 border border-gray-200 rounded-lg p-4 space-y-3">
          <h4 className="text-sm font-medium text-gray-900">
            Summary
          </h4>
          <div className="text-sm text-gray-700 space-y-1">
            <p>
              <span className="font-medium">App:</span>{' '}
              {s.app_name}
            </p>
            <p>
              <span className="font-medium">
                Total Components:
              </span>{' '}
              {s.total_components}
            </p>
            <p>
              <span className="font-medium">Duration:</span>{' '}
              {s.duration_seconds}s
            </p>
          </div>

          {/* Imported counts */}
          {Object.keys(s.components_imported).length > 0 && (
            <div className="border-t border-gray-200 pt-3">
              <p className="text-xs font-medium text-gray-700 mb-1">
                Imported Components
              </p>
              <div className="grid grid-cols-2 gap-1 text-xs text-gray-600">
                {Object.entries(
                  s.components_imported
                ).map(([type, count]) => (
                  <p key={type}>
                    {type}: {count}
                  </p>
                ))}
              </div>
            </div>
          )}

          {/* Warnings */}
          {s.total_warnings.length > 0 && (
            <div className="border-t border-gray-200 pt-3">
              <p className="text-xs font-medium text-amber-700 mb-1">
                Warnings ({s.total_warnings.length})
              </p>
              <ul className="text-xs text-amber-600 space-y-0.5 list-disc list-inside max-h-32 overflow-y-auto">
                {s.total_warnings.map((w) => (
                  <li key={w}>{w}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Errors */}
          {s.total_errors.length > 0 && (
            <div className="border-t border-gray-200 pt-3">
              <p className="text-xs font-medium text-red-700 mb-1">
                Errors ({s.total_errors.length})
              </p>
              <ul className="text-xs text-red-600 space-y-0.5 list-disc list-inside">
                {s.total_errors.map((e) => (
                  <li key={e}>{e}</li>
                ))}
              </ul>
            </div>
          )}
        </div>

        <div className="flex justify-center space-x-3">
          <button
            type="button"
            onClick={onOpenApp}
            className="px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700"
          >
            Open App Dashboard
          </button>
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 text-sm bg-white text-gray-700 border border-gray-300 rounded-lg hover:bg-gray-50"
          >
            Close
          </button>
        </div>
      </div>
    );
  }

  // Failure
  return (
    <div className="space-y-4">
      <Alert
        type="error"
        title="Import Failed"
        message={result.message}
      />
      <div className="flex justify-center space-x-3">
        <button
          type="button"
          onClick={onRetry}
          className="px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700"
        >
          Try Again
        </button>
        <button
          type="button"
          onClick={onClose}
          className="px-4 py-2 text-sm bg-white text-gray-700 border border-gray-300 rounded-lg hover:bg-gray-50"
        >
          Close
        </button>
      </div>
    </div>
  );
}

export default AppStepResult;
