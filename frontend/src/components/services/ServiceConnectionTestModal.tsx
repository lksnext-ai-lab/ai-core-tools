import { CheckCircle2, XCircle } from 'lucide-react';
import Modal from '../ui/Modal';
import type { TestConnectionResult } from './serviceApi';
import type { ServiceKindLabel } from './useServiceConnectionTest';

interface ServiceConnectionTestModalProps {
  readonly isOpen: boolean;
  readonly isTesting: boolean;
  readonly serviceName: string;
  readonly serviceKind: ServiceKindLabel;
  readonly result: TestConnectionResult | null;
  readonly onClose: () => void;
}

function ServiceConnectionTestModal({
  isOpen,
  isTesting,
  serviceName,
  serviceKind,
  result,
  onClose,
}: Readonly<ServiceConnectionTestModalProps>) {
  return (
    <Modal
      isOpen={isOpen}
      onClose={() => !isTesting && onClose()}
      title="Connection Test Result"
      size="medium"
    >
      <div className="space-y-4">
        <div role="status" aria-live="polite" aria-atomic="true">
          {isTesting ? (
            <div className="py-6 text-center">
              <div className="mx-auto mb-4 h-10 w-10 animate-spin rounded-full border-b-2 border-blue-600" aria-hidden="true" />
              <p className="text-gray-600 dark:text-slate-300">
                Testing connection to {serviceKind} service {serviceName}...
              </p>
            </div>
          ) : result && (
            <div
              className={`rounded p-3 ${
                result.status === 'success'
                  ? 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-200'
                  : 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-200'
              }`}
            >
              <div className="flex items-center gap-2">
                {result.status === 'success'
                  ? <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
                  : <XCircle className="h-4 w-4" aria-hidden="true" />}
                <strong>Status:</strong> {result.status === 'success' ? 'Success' : 'Error'}
              </div>
              <p className="mt-1"><strong>Message:</strong> {result.message}</p>
            </div>
          )}
        </div>

        {!isTesting && result?.response && (
          <div>
            <h4 className="mb-2 font-semibold">Response:</h4>
            <div className="max-h-60 overflow-y-auto whitespace-pre-wrap rounded border bg-gray-50 p-3 font-mono text-sm dark:border-slate-600 dark:bg-slate-700">
              {result.response}
            </div>
          </div>
        )}

        {!isTesting && (
          <div className="flex justify-end">
            <button
              type="button"
              onClick={onClose}
              className="rounded bg-gray-200 px-4 py-2 text-gray-800 hover:bg-gray-300 dark:bg-slate-600 dark:text-slate-100 dark:hover:bg-slate-500"
            >
              Close
            </button>
          </div>
        )}
      </div>
    </Modal>
  );
}

export default ServiceConnectionTestModal;
