import { ExternalLink } from 'lucide-react';
import { FormField } from '../../../ui/FormField';
import Alert from '../../../ui/Alert';
import { getProviderDescriptor } from '../providers';
import type { ServiceKind, ServiceWizardMode } from '../../../../types/services';

/** Provider-specific label for the secret field. */
const API_KEY_LABELS: Record<string, string> = {
  GoogleCloud: 'Service Account JSON',
  Bedrock: 'AWS Secret Access Key',
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
  const descriptor = getProviderDescriptor(provider);

  if (!descriptor) {
    return (
      <Alert
        type="error"
        title="Provider not found"
        message="Go back and pick a provider before continuing."
      />
    );
  }

  const update = (patch: Partial<CredentialsState>) =>
    onChange({ ...value, ...patch });
  const manualFields = descriptor.manualFields ?? [];

  const apiKeyBaseLabel = API_KEY_LABELS[descriptor.value] ?? 'API Key';
  const apiKeyLabel = `${apiKeyBaseLabel}${
    descriptor.apiKey === 'optional' ? ' (optional)' : ''
  }`;

  let baseUrlLabel = 'Base URL';
  if (descriptor.value === 'GoogleCloud') baseUrlLabel = 'GCP Project ID';
  else if (descriptor.value === 'Azure') baseUrlLabel = 'Azure endpoint';
  else if (descriptor.value === 'opensandbox') baseUrlLabel = 'OpenSandbox server domain';
  else if (descriptor.value === 'daytona') baseUrlLabel = 'Daytona API URL';

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-base font-semibold text-gray-900">
          Enter credentials for {descriptor.label}
        </h3>
        <p className="text-sm text-gray-600 mt-1">
          These credentials are used to fetch the available models. They are not
          saved until you confirm the service in the final step.
        </p>
      </div>

      {mode === 'edit-model' && (
        <Alert
          type="info"
          message="Re-enter the API key — the masked value cannot be used to list models."
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
            helpText={descriptor.apiKeyHelp}
            required={descriptor.apiKey === 'required'}
          />
          {descriptor.apiKeyDocUrl && (
            <a
              href={descriptor.apiKeyDocUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="mt-1.5 inline-flex items-center gap-1 text-xs font-medium text-blue-600 hover:text-blue-800"
            >
              <ExternalLink className="w-3 h-3" />
              {descriptor.value === 'GoogleCloud'
                ? 'Open Google Cloud Console'
                : `Get a ${descriptor.label} key`}
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
          label={descriptor.value === 'GoogleCloud' ? 'Region (location)' : 'API version'}
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
          label="AWS Access Key ID"
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
          label="AWS Region"
          id="aws_region"
          type="text"
          value={value.aws_region ?? ''}
          onChange={(e) => update({ aws_region: e.target.value })}
          placeholder="us-east-1"
          helpText="Region where Bedrock is enabled, e.g. us-east-1 or eu-west-1."
          required
        />
      )}

      {manualFields.includes('image') && (
        <FormField
          label="Container image"
          id="image"
          type="text"
          value={value.image ?? ''}
          onChange={(e) => update({ image: e.target.value })}
          placeholder="python:3.11-slim"
          helpText="Docker image used to create sandbox containers. Leave empty to use the server default."
        />
      )}

      {manualFields.includes('target') && (
        <FormField
          label="Target"
          id="target"
          type="text"
          value={value.target ?? ''}
          onChange={(e) => update({ target: e.target.value })}
          placeholder="us"
          helpText="Daytona target/region identifier. Leave empty to use the account default."
        />
      )}

      {manualFields.includes('template') && (
        <FormField
          label="Template"
          id="template"
          type="text"
          value={value.template ?? ''}
          onChange={(e) => update({ template: e.target.value })}
          placeholder="base"
          helpText="E2B sandbox template id. Leave empty to use the default template."
        />
      )}

      {descriptor.value === 'Bedrock' && (
        <Alert
          type="info"
          title="Model access may be required"
          message="A listed model still needs to be enabled in the AWS console (Bedrock → Model access) before it can be invoked."
        />
      )}

      {kind !== 'sandbox' && !descriptor.supportsModelListing && (
        <Alert
          type="info"
          title="Manual model entry"
          message="This provider does not expose a public model listing. The next step will ask you to type the model identifier directly."
        />
      )}
    </div>
  );
}

export default CredentialsStep;
