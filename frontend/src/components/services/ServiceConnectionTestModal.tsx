import Modal from '../ui/Modal';
import Alert from '../ui/Alert';
import { ButtonApp } from '../ui/ButtonApp';
import LoadingState from '../ui/LoadingState';
import { useTranslation } from 'react-i18next';
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
  const { t } = useTranslation('common');
  const serviceKindTranslationKey = {
    AI: 'connectionTestResult.serviceKinds.ai',
    embedding: 'connectionTestResult.serviceKinds.embedding',
    sandbox: 'connectionTestResult.serviceKinds.sandbox',
  }[serviceKind];

  return (
    <Modal
      isOpen={isOpen}
      onClose={() => !isTesting && onClose()}
      title={t('connectionTestResult.title')}
      size="medium"
    >
      <div className="space-y-4">
        {isTesting ? (
          <LoadingState
            variant="section"
            className="py-6"
            message={t('connectionTestResult.testing', {
              serviceKind: t(serviceKindTranslationKey),
              serviceName,
            })}
          />
        ) : result && (
          <Alert
            type={result.status === 'success' ? 'success' : 'error'}
            title={t('connectionTestResult.statusTitle', {
              status: t(`connectionTestResult.status.${result.status}`),
            })}
            message={<><strong>{t('connectionTestResult.message')}:</strong> {result.message}</>}
            polite={result.status === 'success'}
          />
        )}

        {!isTesting && result?.response && (
          <div>
            <h4 className="mb-2 font-semibold">{t('connectionTestResult.response')}:</h4>
            <div className="max-h-60 overflow-y-auto whitespace-pre-wrap rounded bg-canvas-alt dark:bg-canvas-alt-dark p-3 text-sm text-fg dark:text-fg-dark">
              {result.response}
            </div>
          </div>
        )}

        {!isTesting && (
          <div className="flex justify-end">
            <ButtonApp
              label={t('connectionTestResult.close')}
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
