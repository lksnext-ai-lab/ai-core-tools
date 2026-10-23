import Modal from '../ui/Modal';
import Alert from '../ui/Alert';
import { ButtonApp } from '../ui/ButtonApp';
import LoadingState from '../ui/LoadingState';
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
        {isTesting ? (
          <LoadingState
            variant="section"
            className="py-6"
            message={`Testing connection to ${serviceKind} service ${serviceName}...`}
          />
        ) : result && (
          <Alert
            type={result.status === 'success' ? 'success' : 'error'}
            title={`Status: ${result.status === 'success' ? 'Success' : 'Error'}`}
            message={<><strong>Message:</strong> {result.message}</>}
            polite={result.status === 'success'}
          />
        )}

        {!isTesting && result?.response && (
          <div>
            <h4 className="mb-2 font-semibold">Response:</h4>
            <div className="max-h-60 overflow-y-auto whitespace-pre-wrap rounded bg-canvas-alt dark:bg-canvas-alt-dark p-3 text-sm text-fg dark:text-fg-dark">
              {result.response}
            </div>
          </div>
        )}

        {!isTesting && (
          <div className="flex justify-end">
            <ButtonApp
              label="Close"
              type="button"
              onClick={onClose}
              variant="secondary"
              size="medium"
            />
          </div>
        )}
      </div>
    </Modal>
  );
}

export default ServiceConnectionTestModal;
