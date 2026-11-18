import { Plug } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { FormCheckbox, FormField } from '../../../ui/FormField';
import Alert from '../../../ui/Alert';
import { Badge } from '../../../ui/Badge';
import { getProviderDescriptor } from '../providers';
import type {
  ProviderModelInfo,
  ServiceKind,
} from '../../../../types/services';
import type { CredentialsState } from './CredentialsStep';
import type { TestConnectionResult } from '../../serviceApi';
import { ButtonApp } from '../../../ui/ButtonApp';
import { CardApp } from '../../../ui/CardApp';

interface ConfirmStepProps {
  readonly kind: ServiceKind;
  readonly provider: string;
  readonly model: ProviderModelInfo | null;
  readonly manualModelName: string;
  readonly serviceName: string;
  readonly onServiceNameChange: (value: string) => void;
  readonly credentials: CredentialsState;
  readonly supportsVideo: boolean;
  readonly onSupportsVideoChange: (value: boolean) => void;
  readonly onTest: () => void | Promise<void>;
  readonly testing: boolean;
  readonly testResult: TestConnectionResult | null;
}

function ConfirmStep({
  kind,
  provider,
  model,
  manualModelName,
  serviceName,
  onServiceNameChange,
  credentials,
  supportsVideo,
  onSupportsVideoChange,
  onTest,
  testing,
  testResult,
}: Readonly<ConfirmStepProps>) {
  const { t } = useTranslation('common');
  const descriptor = getProviderDescriptor(provider);
  const isManual = !descriptor?.supportsModelListing;
  const modelLabel = isManual ? manualModelName : model?.display_name || '—';
  const modelId = isManual ? manualModelName : model?.id || '';
  const capabilityLabels = model
    ? [
        { enabled: model.capabilities.chat, labelKey: 'chat' },
        { enabled: model.capabilities.vision, labelKey: 'vision' },
        { enabled: model.capabilities.audio, labelKey: 'audio' },
        { enabled: model.capabilities.reasoning, labelKey: 'reasoning' },
        { enabled: model.capabilities.function_calling, labelKey: 'tools' },
        { enabled: model.capabilities.embedding, labelKey: 'embedding' },
      ].filter(({ enabled }) => enabled)
    : [];

  const showSupportsVideo =
    kind === 'ai' && (provider === 'Google' || provider === 'GoogleCloud');

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-base font-semibold text-fg dark:text-fg-dark">{t('serviceWizard.confirmStep.title')}</h3>
        <p className="text-sm text-fg-secondary dark:text-fg-secondary-dark mt-1">
          {t('serviceWizard.confirmStep.subtitle')}
        </p>
      </div>

      <CardApp variant="white" className="!p-0 divide-y divide-line dark:divide-btCard-border-dark">
        <Row label={t('serviceWizard.confirmStep.name')} >
          <FormField
            id="service-name"
            value={serviceName}
            ariaLabel={t('serviceWizard.confirmStep.name')}
            onChange={(event) => onServiceNameChange(event.target.value)}
            required
          />
        </Row>

        <Row label={t('serviceWizard.confirmStep.provider')}>
          <span className="text-sm text-fg-secondary dark:text-fg-secondary-dark">{descriptor?.label || provider}</span>
        </Row>

        {kind !== 'sandbox' && (
          <Row label={t('serviceWizard.confirmStep.model')}>
            <div className="flex flex-col gap-2 lg:flex-row lg:items-start lg:justify-between">
              <div className="min-w-0">
                <p className="text-sm font-medium text-fg-secondary dark:text-fg-secondary-dark">{modelLabel}</p>
                {modelId && modelId !== modelLabel && (
                  <p className="text-xs font-mono text-fg-secondary dark:text-fg-secondary-dark mt-0.5">{modelId}</p>
                )}
              </div>
              {capabilityLabels.length > 0 && (
                <div className="flex flex-wrap gap-1 lg:justify-end">
                  {capabilityLabels.map(({ labelKey }) => (
                    <Badge
                      key={labelKey}
                      label={t(`serviceWizard.confirmStep.capabilities.${labelKey}`)}
                      variant="default"
                    />
                  ))}
                </div>
              )}
            </div>
          </Row>
        )}

        {credentials.base_url && (
          <Row label={provider === 'GoogleCloud'
            ? t('serviceWizard.confirmStep.projectId')
            : t('serviceWizard.confirmStep.endpoint')}>
            <span className="text-sm text-fg-secondary dark:text-fg-secondary-dark font-mono break-all">
              {credentials.base_url}
            </span>
          </Row>
        )}

        {credentials.api_version && (
          <Row label={provider === 'GoogleCloud'
            ? t('serviceWizard.confirmStep.region')
            : t('serviceWizard.confirmStep.apiVersion')}>
            <span className="text-sm text-fg-secondary dark:text-fg-secondary-dark font-mono">
              {credentials.api_version}
            </span>
          </Row>
        )}

        {credentials.image && (
          <Row label={t('serviceWizard.confirmStep.containerImage')}>
            <span className="text-sm text-fg-secondary dark:text-fg-secondary-dark font-mono break-all">{credentials.image}</span>
          </Row>
        )}

        {credentials.target && (
          <Row label={t('serviceWizard.confirmStep.target')}>
            <span className="text-sm text-fg-secondary dark:text-fg-secondary-dark font-mono">{credentials.target}</span>
          </Row>
        )}

        {credentials.template && (
          <Row label={t('serviceWizard.confirmStep.template')}>
            <span className="text-sm text-fg-secondary dark:text-fg-secondary-dark font-mono">{credentials.template}</span>
          </Row>
        )}

        {descriptor?.apiKey !== 'none' && credentials.api_key && (
          <Row label={t('serviceWizard.confirmStep.apiKey')}>
            <span className="text-sm font-mono text-fg-secondary dark:text-fg-secondary-dark">
              {maskKey(credentials.api_key)}
            </span>
          </Row>
        )}
      </CardApp>

      {showSupportsVideo && (
        <FormCheckbox
          id="supports_video"
          label={t('serviceWizard.confirmStep.videoAnalysisCapable')}
          checked={supportsVideo}
          onChange={(e) => onSupportsVideoChange(e.target.checked)}
          helpText={t('serviceWizard.confirmStep.videoAnalysisHelp')}
        />
      )}

      <TestConnectionPanel
        onTest={onTest}
        testing={testing}
        result={testResult}
      />

      {model?.deprecated && (
        <Alert
          type="warning"
          title={t('serviceWizard.confirmStep.deprecatedModelTitle')}
          message={t('serviceWizard.confirmStep.deprecatedModelMessage')}
        />
      )}
    </div>
  );
}

interface TestConnectionPanelProps {
  readonly onTest: () => void | Promise<void>;
  readonly testing: boolean;
  readonly result: TestConnectionResult | null;
}

function TestConnectionPanel({
  onTest,
  testing,
  result,
}: Readonly<TestConnectionPanelProps>) {
  const { t } = useTranslation('common');
  return (
    <CardApp className="p-3 space-y-2">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-sm font-medium text-fg-secondary dark:text-fg-secondary-dark">{t('serviceWizard.confirmStep.testConnection')}</p>
          <p className="text-xs text-fg-secondary dark:text-fg-secondary-dark">
            {t('serviceWizard.confirmStep.testConnectionHelp')}
          </p>
        </div>
        <ButtonApp
          label={testing
            ? t('serviceWizard.confirmStep.testing')
            : t('serviceWizard.confirmStep.runTest')}
          onClick={() => void onTest()}
          loading={testing}
          variant="secondary"
          size="compact"
          icon={<Plug className="w-3.5 h-3.5" />}
        />
      </div>

      {result && (
        <Alert
          type={result.status === 'success' ? 'success' : 'error'}
          title={result.status === 'success'
            ? t('serviceWizard.confirmStep.connectionSuccessful')
            : t('serviceWizard.confirmStep.connectionFailed')}
          message={(
            <>
              <span className="text-xs break-words">{result.message}</span>
              {result.response && (
                <span className="mt-1 block text-xs font-mono break-words">
                  {result.response.length > 200
                    ? `${result.response.slice(0, 200)}…`
                    : result.response}
                </span>
              )}
            </>
          )}
        />
      )}
    </CardApp>
  );
}

function Row({ label, children }: { readonly label: string; readonly children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-3 gap-3 px-4 py-3">
      <dt className="text-xs uppercase tracking-wide text-fg-tertiary dark:text-fg-tertiary-dark font-semibold pt-0.5">
        {label}
      </dt>
      <dd className="col-span-2">{children}</dd>
    </div>
  );
}

function maskKey(key: string): string {
  if (!key) return '—';
  if (key.length <= 4) return '****';
  return `****${key.slice(-4)}`;
}

export default ConfirmStep;
