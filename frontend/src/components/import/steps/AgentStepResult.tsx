import Alert from '../../ui/Alert';
import type { ImportResponse } from '../../../types/import';

interface Props {
  result: ImportResponse | null;
  isImporting: boolean;
  importError: string | null;
  onClose: () => void;
  onViewAgent: () => void;
  onRetry: () => void;
}

function AgentStepResult({
  result,
  isImporting,
  importError,
  onClose,
  onViewAgent,
  onRetry,
}: Props) {
  if (isImporting) {
    return (
      <div className="flex flex-col items-center justify-center py-12 space-y-4">
        <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-blue-600" />
        <p className="text-sm text-gray-600">
          Importing agent...
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

  if (result.success) {
    return (
      <div className="space-y-4">
        <Alert
          type="success"
          title="Import Successful"
          message={result.message}
        />

        {result.summary && (
          <div className="bg-gray-50 border border-gray-200 rounded-lg p-4 space-y-3">
            <h4 className="text-sm font-medium text-gray-900">
              Summary
            </h4>
            <div className="text-sm text-gray-700 space-y-1">
              <p>
                <span className="font-medium">Component:</span>{' '}
                {result.summary.component_name}
              </p>
              {result.summary.mode && (
                <p>
                  <span className="font-medium">Mode:</span>{' '}
                  {result.summary.mode}
                </p>
              )}
              <p>
                <span className="font-medium">Created:</span>{' '}
                {result.summary.created ? 'Yes' : 'Updated'}
              </p>
            </div>

            {result.summary.warnings &&
              result.summary.warnings.length > 0 && (
                <div className="border-t border-gray-200 pt-3">
                  <p className="text-xs font-medium text-amber-700 mb-1">
                    Warnings
                  </p>
                  <ul className="text-xs text-amber-600 space-y-0.5 list-disc list-inside">
                    {result.summary.warnings.map(
                      (w, i) => (
                        <li key={i}>{w}</li>
                      )
                    )}
                  </ul>
                </div>
              )}

            {result.summary.next_steps &&
              result.summary.next_steps.length > 0 && (
                <div className="border-t border-gray-200 pt-3">
                  <p className="text-xs font-medium text-blue-700 mb-1">
                    Next Steps
                  </p>
                  <ul className="text-xs text-blue-600 space-y-0.5 list-disc list-inside">
                    {result.summary.next_steps.map(
                      (s, i) => (
                        <li key={i}>{s}</li>
                      )
                    )}
                  </ul>
                </div>
              )}
          </div>
        )}

        <div className="flex justify-center space-x-3">
          {result.summary?.component_id && (
            <button
              type="button"
              onClick={onViewAgent}
              className="px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700"
            >
              View Agent
            </button>
          )}
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

  // Failure case
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

export default AgentStepResult;
