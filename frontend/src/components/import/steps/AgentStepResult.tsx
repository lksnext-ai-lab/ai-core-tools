import Alert from '../../ui/Alert';
import ButtonApp from '../../ui/ButtonApp';
import type { ImportResponse } from '../../../types/import';
import { LoadingState } from '../../ui/LoadingState';
import { useTranslation } from 'react-i18next';
import CardApp from '../../ui/CardApp';

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
}: Readonly<Props>) {
  const { t } = useTranslation('common');

  if (isImporting) {
    return (
      <LoadingState
        variant="section"
        message={t('importModal.agentResult.importing')}
      />
    );
  }

  if (importError) {
    return (
      <div className="space-y-4">
        <Alert type="error" message={importError} />
        <div className="flex justify-center space-x-3">
          <ButtonApp
            label={t('importModal.agentResult.tryAgain')}
            type="button"
            onClick={onRetry}
            variant="primary"
            size="medium"
          />
          <ButtonApp
            label={t('importModal.actions.close')}
            type="button"
            onClick={onClose}
            variant="secondary"
            size="medium"
          />
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
          title={t('importModal.result.success')}
          message={result.message}
        />

        {result.summary && (
          <CardApp className="p-4 space-y-3" titulo={t('importModal.result.summary')}>
            <div className="text-sm text-fg dark:text-fg-dark space-y-1">
              <p>
                <span className="font-medium">
                  {t('importModal.result.component')}:
                </span>{' '}
                {result.summary.component_name}
              </p>
              {result.summary.mode && (
                <p>
                  <span className="font-medium">
                    {t('importModal.agentResult.mode')}:
                  </span>{' '}
                  {t(`importModal.conflict.options.${result.summary.mode}`)}
                </p>
              )}
              <p>
                <span className="font-medium">
                  {t('importModal.result.created')}:
                </span>{' '}
                {result.summary.created
                  ? t('importModal.agentResult.yes')
                  : t('importModal.result.updated')}
              </p>
            </div>

            {result.summary.warnings &&
              result.summary.warnings.length > 0 && (
                <Alert
                  type="warning"
                  title={t('importModal.result.warnings')}
                  message={
                    <ul className="list-disc list-inside space-y-0.5">
                      {result.summary.warnings.map((w) => (
                        <li key={w}>{w}</li>
                      ))}
                    </ul>
                  }
                  className="mt-3"
                />
              )}

            {result.summary.next_steps &&
              result.summary.next_steps.length > 0 && (
                <Alert
                  type="info"
                  title={t('importModal.result.nextSteps')}
                  message={
                    <ul className="list-disc list-inside space-y-0.5">
                      {result.summary.next_steps.map((s) => (
                        <li key={s}>{s}</li>
                      ))}
                    </ul>
                  }
                  className="mt-3"
                />
              )}
          </CardApp>
        )}

        <div className="flex justify-center space-x-3">
          {result.summary?.component_id && (
            <ButtonApp
              label={t('importModal.agentResult.viewAgent')}
              type="button"
              onClick={onViewAgent}
              variant="primary"
              size="medium"
            />
          )}
          <ButtonApp
            label={t('importModal.actions.close')}
            type="button"
            onClick={onClose}
            variant="secondary"
            size="medium"
          />
        </div>
      </div>
    );
  }

  // Failure case
  return (
    <div className="space-y-4">
      <Alert
        type="error"
        title={t('importModal.errors.importFailed')}
        message={result.message}
      />
      <div className="flex justify-center space-x-3">
        <ButtonApp
          label={t('importModal.agentResult.tryAgain')}
          type="button"
          onClick={onRetry}
          variant="primary"
          size="medium"
        />
        <ButtonApp
          label={t('importModal.actions.close')}
          type="button"
          onClick={onClose}
          variant="secondary"
          size="medium"
        />
      </div>
    </div>
  );
}

export default AgentStepResult;
