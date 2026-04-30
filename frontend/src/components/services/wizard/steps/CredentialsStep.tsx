import { ExternalLink } from 'lucide-react';
import { FormField } from '../../../ui/FormField';
import Alert from '../../../ui/Alert';
import { getProviderDescriptor } from '../providers';
import type { ServiceWizardMode } from '../../../../types/services';

export interface CredentialsState {
  api_key: string;
  /** For Azure: endpoint URL. For GoogleCloud: GCP project id. For
   *  Ollama/Self-hosted: the host URL. Not used by providers that talk
   *  to a fixed cloud endpoint (OpenAI, Anthropic, MistralAI, Google AI Studio). */
  base_url: string;
  /** For Azure: API version. For GoogleCloud: region/location. */
  api_version: string;
}

interface CredentialsStepProps {
  readonly provider: string;
  readonly mode: ServiceWizardMode;
  readonly value: CredentialsState;
  readonly onChange: (next: CredentialsState) => void;
}

function CredentialsStep({
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

  const apiKeyLabel = `${
    descriptor.value === 'GoogleCloud' ? 'Service Account JSON' : 'API Key'
  }${descriptor.apiKey === 'optional' ? ' (optional)' : ''}`;

  let baseUrlLabel = 'Base URL';
  if (descriptor.value === 'GoogleCloud') baseUrlLabel = 'GCP Project ID';
  else if (descriptor.value === 'Azure') baseUrlLabel = 'Azure endpoint';

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

      {!descriptor.supportsModelListing && (
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
