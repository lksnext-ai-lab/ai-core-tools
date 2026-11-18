import { ExternalLink } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { FormField } from '../../../ui/FormField';
import Alert from '../../../ui/Alert';
import { getProviderDescriptor } from '../providers';
import type { ServiceKind, ServiceWizardMode } from '../../../../types/services';

/** Provider-specific label for the secret field. */
const API_KEY_LABELS: Record<string, string> = {
  GoogleCloud: 'serviceWizard.credentialsStep.apiKeyLabels.serviceAccountJson',
  Bedrock: 'serviceWizard.credentialsStep.apiKeyLabels.awsSecretAccessKey',
};

const API_KEY_HELP_KEYS: Record<string, string> = {
  'ai:OpenAI': 'openAI',
  'ai:Anthropic': 'anthropic',
  'ai:OpenRouter': 'openRouter',
  'ai:MistralAI': 'mistralAI',
  'ai:Google': 'google',
  'ai:Custom': 'selfHosted',
  'embedding:Custom': 'huggingFace',
  'embedding:Ollama': 'ollama',
  'embedding:MistralAI': 'mistralAI',
  'ai:Azure': 'azure',
  'embedding:Azure': 'azure',
  'ai:GoogleCloud': 'googleCloud',
  'embedding:GoogleCloud': 'googleCloud',
  'ai:Bedrock': 'bedrock',
  'embedding:Bedrock': 'bedrock',
  'sandbox:opensandbox': 'openSandbox',
  'sandbox:daytona': 'daytona',
  'sandbox:e2b': 'e2b',
};

export interface CredentialsState {
  api_key: string;
  /** For Azure: endpoint URL. For GoogleCloud: GCP project id. For
   *  Ollama/Self-hosted: the host URL. Not used by providers that talk
   *  to a fixed cloud endpoint (OpenAI, Anthropic, MistralAI, Google AI Studio). */
  base_url: string;
  /** For Azure: API version. For GoogleCloud: region/location. */
  api_version: string;
  /** AWS Bedrock: Access Key ID (non-secret). */
  aws_access_key_id?: string;
  /** AWS Bedrock: region, e.g. us-east-1. */
  aws_region?: string;
  /** Sandbox (OpenSandbox): container image used to create sandboxes. */
  image?: string;
  /** Sandbox (Daytona): target/region identifier. */
  target?: string;
  /** Sandbox (E2B): template id used to create sandboxes. */
  template?: string;
}

interface CredentialsStepProps {
  readonly kind: ServiceKind;
  readonly provider: string;
  readonly mode: ServiceWizardMode;
  readonly value: CredentialsState;
  readonly onChange: (next: CredentialsState) => void;
}

function CredentialsStep({
  kind,
  provider,
  mode,
  value,
  onChange,
}: Readonly<CredentialsStepProps>) {
  const { t } = useTranslation('common');
  const descriptor = getProviderDescriptor(provider);

  if (!descriptor) {
    return (
      <Alert
        type="error"
        title={t('serviceWizard.credentialsStep.providerNotFound')}
        message={t('serviceWizard.credentialsStep.pickProviderFirst')}
      />
    );
  }

  const update = (patch: Partial<CredentialsState>) =>
    onChange({ ...value, ...patch });
  const manualFields = descriptor.manualFields ?? [];

  const apiKeyBaseLabel = t(API_KEY_LABELS[descriptor.value] ?? 'serviceWizard.credentialsStep.apiKey');
  let apiKeyLabel = apiKeyBaseLabel;
  if (descriptor.apiKey === 'optional') {
    apiKeyLabel += ` (${t('serviceWizard.credentialsStep.optional')})`;
  }

  let baseUrlLabel = t('serviceWizard.credentialsStep.baseUrl');
  if (descriptor.value === 'GoogleCloud') baseUrlLabel = t('serviceWizard.credentialsStep.gcpProjectId');
  else if (descriptor.value === 'Azure') baseUrlLabel = t('serviceWizard.credentialsStep.azureEndpoint');
  else if (descriptor.value === 'opensandbox') baseUrlLabel = t('serviceWizard.credentialsStep.openSandboxDomain');
  else if (descriptor.value === 'daytona') baseUrlLabel = t('serviceWizard.credentialsStep.daytonaApiUrl');
  const apiKeyHelpKey = API_KEY_HELP_KEYS[`${kind}:${descriptor.value}`] ?? 'default';

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-base font-semibold text-fg dark:text-fg-dark">
          {t('serviceWizard.credentialsStep.title', { provider: descriptor.label })}
        </h3>
        <p className="text-sm text-fg-secondary dark:text-fg-secondary-dark mt-1">
          {t('serviceWizard.credentialsStep.subtitle')}
        </p>
      </div>

      {mode === 'edit-model' && (
        <Alert
          type="info"
          message={t('serviceWizard.credentialsStep.reenterApiKey')}
        />
      )}

      {descriptor.apiKey !== 'none' && (
        <div>
          <FormField
            label={apiKeyLabel}
            id="api_key"
            type="password"
            value={value.api_key}
            onChange={(e) => update({ api_key: e.target.value })}
            placeholder={descriptor.apiKeyPlaceholder}
            helpText={t(`serviceWizard.credentialsStep.apiKeyHelp.${apiKeyHelpKey}`)}
            required={descriptor.apiKey === 'required'}
          />
          {descriptor.apiKeyDocUrl && (
            <a
              href={descriptor.apiKeyDocUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="text-sm text-bronze  dark:text-bronze-dark inline-block"
            >
              
              {descriptor.value === 'GoogleCloud'
                ? t('serviceWizard.credentialsStep.openGoogleCloudConsole')
                : t('serviceWizard.credentialsStep.getProviderKey', { provider: descriptor.label })}
              <ExternalLink className="w-4 h-4 inline-block ml-1" />
            </a>
          )}
        </div>
      )}

      {descriptor.needsBaseUrl && (
        <FormField
          label={baseUrlLabel}
          id="base_url"
          type="text"
          value={value.base_url}
          onChange={(e) => update({ base_url: e.target.value })}
          placeholder={descriptor.baseUrlPlaceholder}
          required
        />
      )}

      {manualFields.includes('api_version') && (
        <FormField
          label={descriptor.value === 'GoogleCloud'
            ? t('serviceWizard.credentialsStep.regionLocation')
            : t('serviceWizard.credentialsStep.apiVersion')}
          id="api_version"
          type="text"
          value={value.api_version}
          onChange={(e) => update({ api_version: e.target.value })}
          placeholder={
            descriptor.value === 'GoogleCloud' ? 'europe-west1' : '2024-08-01-preview'
          }
        />
      )}

      {manualFields.includes('aws_access_key_id') && (
        <FormField
          label={t('serviceWizard.credentialsStep.awsAccessKeyId')}
          id="aws_access_key_id"
          type="text"
          value={value.aws_access_key_id ?? ''}
          onChange={(e) => update({ aws_access_key_id: e.target.value })}
          placeholder="AKIA..."
          required
        />
      )}

      {manualFields.includes('aws_region') && (
        <FormField
          label={t('serviceWizard.credentialsStep.awsRegion')}
          id="aws_region"
          type="text"
          value={value.aws_region ?? ''}
          onChange={(e) => update({ aws_region: e.target.value })}
          placeholder="us-east-1"
          helpText={t('serviceWizard.credentialsStep.awsRegionHelp')}
          required
        />
      )}

      {manualFields.includes('image') && (
        <FormField
          label={t('serviceWizard.credentialsStep.containerImage')}
          id="image"
          type="text"
          value={value.image ?? ''}
          onChange={(e) => update({ image: e.target.value })}
          placeholder="python:3.11-slim"
          helpText={t('serviceWizard.credentialsStep.containerImageHelp')}
        />
      )}

      {manualFields.includes('target') && (
        <FormField
          label={t('serviceWizard.credentialsStep.target')}
          id="target"
          type="text"
          value={value.target ?? ''}
          onChange={(e) => update({ target: e.target.value })}
          placeholder="us"
          helpText={t('serviceWizard.credentialsStep.targetHelp')}
        />
      )}

      {manualFields.includes('template') && (
        <FormField
          label={t('serviceWizard.credentialsStep.template')}
          id="template"
          type="text"
          value={value.template ?? ''}
          onChange={(e) => update({ template: e.target.value })}
          placeholder="base"
          helpText={t('serviceWizard.credentialsStep.templateHelp')}
        />
      )}

      {descriptor.value === 'Bedrock' && (
        <Alert
          type="info"
          title={t('serviceWizard.credentialsStep.modelAccessTitle')}
          message={t('serviceWizard.credentialsStep.modelAccessMessage')}
        />
      )}

      {kind !== 'sandbox' && !descriptor.supportsModelListing && (
        <Alert
          type="info"
          title={t('serviceWizard.credentialsStep.manualModelTitle')}
          message={t('serviceWizard.credentialsStep.manualModelMessage')}
        />
      )}
    </div>
  );
}

export default CredentialsStep;
