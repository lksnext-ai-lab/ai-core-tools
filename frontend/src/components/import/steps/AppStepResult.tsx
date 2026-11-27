import Alert from '../../ui/Alert';
import ButtonApp from '../../ui/ButtonApp';
import type { FullAppImportResponse } from '../../../types/import';
import { LoadingState } from '../../ui/LoadingState';
import CardApp from '../../ui/CardApp';
import { useTranslation } from 'react-i18next';

interface Props {
  result: FullAppImportResponse | null;
  isImporting: boolean;
  importError: string | null;
  onClose: () => void;
  onOpenApp: () => void;
  onRetry: () => void;
}

const COMPONENT_TYPE_TRANSLATION_KEYS: Record<string, string> = {
  ai_service: 'aiServices',
  embedding_service: 'embeddingServices',
  output_parser: 'outputParsers',
  mcp_config: 'mcpConfigs',
  silo: 'silos',
  repository: 'repositories',
  domain: 'domains',
  agent: 'agents',
  app: 'apps',
};

function AppStepResult({
  result,
  isImporting,
  importError,
  onClose,
  onOpenApp,
  onRetry,
}: Readonly<Props>) {
  const { t } = useTranslation('common');

  if (isImporting) {
    return (
      <LoadingState
        variant="section"
        message={t('importModal.appResult.importing')}
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

  if (result.success && result.summary) {
    const s = result.summary;
    return (
      <div className="space-y-4">
        <Alert
          type="success"
          title={t('importModal.result.success')}
          message={result.message}
        />

        <CardApp
          className="p-4 space-y-3"
          titulo={t('importModal.result.summary')}
        >
          <div className="text-sm ">
            <p>
              <span className="text-bornza-dark uppercase">
                {t('importModal.appResult.app')}:
              </span>{' '}
              <span className="text-fg dark:text-fg-dark uppercase">{s.app_name}</span>
            </p>
            <p>
              <span className="text-bornza-dark uppercase">
                {t('importModal.appResult.totalComponents')}:
              </span>{' '}
              <span className="text-fg dark:text-fg-dark uppercase">{s.total_components}</span>
            </p>
            <p>
              <span className="text-bornza-dark uppercase">
                {t('importModal.appResult.duration')}:
              </span>{' '}
              <span className="text-fg dark:text-fg-dark uppercase">{s.duration_seconds}</span>s
            </p>
          </div>

          {/* Imported counts */}
          {Object.keys(s.components_imported).length > 0 && (
            <div className="pt-3">
              <p className="text-xs text-fg dark:text-fg-dark mb-1">
                {t('importModal.appResult.importedComponents')}
              </p>
              <div className="grid grid-cols-2 gap-1 text-xs text-fg-secondary dark:text-fg-secondary-dark">
                {Object.entries(
                  s.components_imported
                ).map(([type, count]) => {
                  const translationKey = COMPONENT_TYPE_TRANSLATION_KEYS[type];
                  const label = translationKey
                    ? t(`importModal.appUpload.components.${translationKey}`, {
                        count,
                      })
                    : type;

                  return (
                    <p key={type}>
                      {label}: {count}
                    </p>
                  );
                })}
              </div>
            </div>
          )}

          {/* Warnings */}
          {s.total_warnings.length > 0 && (
            <Alert
              type="warning"
              title={t('importModal.appResult.warnings', {
                count: s.total_warnings.length,
              })}
              message={(
                <ul className="list-disc list-inside space-y-0.5 max-h-32 overflow-y-auto">
                  {s.total_warnings.map((w) => (
                    <li key={w}>{w}</li>
                  ))}
                </ul>
              )}
              className="mt-3"
            />
          )}

          {/* Errors */}
          {s.total_errors.length > 0 && (
            <Alert
              type="error"
              title={t('importModal.appResult.errors', {
                count: s.total_errors.length,
              })}
              message={(
                <ul className="list-disc list-inside space-y-0.5">
                  {s.total_errors.map((e) => (
                    <li key={e}>{e}</li>
                  ))}
                </ul>
              )}
              className="mt-3"
            />
          )}
        </CardApp>

        <div className="flex justify-center space-x-3">
          <ButtonApp
            label={t('importModal.appResult.openAppDashboard')}
            type="button"
            onClick={onOpenApp}
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

  // Failure
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

export default AppStepResult;
