import { useEffect, useMemo, useState } from 'react';
import { Pencil } from 'lucide-react';
import Modal from '../ui/Modal';
import { FormField, FormCheckbox } from '../ui/FormField';
import FormActions from '../forms/FormActions';
import Alert from '../ui/Alert';
import { getProviderBadgeColor } from '../ui/providerBadges';
import { getProviderDescriptor } from './wizard/providers';
import ServiceWizard from './wizard/ServiceWizard';
import type {
  ExistingSandboxService,
  ExistingService,
  SandboxServiceFormData,
  ServiceFormData,
  ServiceKind,
  ServiceScope,
} from '../../types/services';

const MASKED_KEY_PREFIX = '****';

/** Provider-specific label for the secret field. */
const API_KEY_LABELS: Record<string, string> = {
  GoogleCloud: 'Service Account JSON',
  Bedrock: 'AWS Secret Access Key',
};

interface CompactServiceEditorProps {
  readonly isOpen: boolean;
  readonly kind: ServiceKind;
  readonly scope: ServiceScope;
  readonly appId?: number;
  readonly service: ExistingService | ExistingSandboxService;
  readonly existingNames?: readonly string[];
  readonly onClose: () => void;
  /**
   * Method shorthand on purpose — see the identical note on
   * `ServiceWizardProps.onSave` for why this keeps bivariant parameter
   * checking so single-kind callers can keep a narrower handler type.
   */
  onSave(data: ServiceFormData | SandboxServiceFormData): Promise<void>;
}

function CompactServiceEditor({
  isOpen,
  kind,
  scope,
  appId,
  service,
  existingNames = [],
  onClose,
  onSave,
}: Readonly<CompactServiceEditorProps>) {
  const isSandbox = kind === 'sandbox';
  // Narrowed views of `service` — the two shapes only overlap on
  // name/provider/api_key/base_url/service_id. Field access for the
  // kind-specific extras goes through these instead of `service` directly.
  const aiService = !isSandbox ? (service as ExistingService) : null;
  const sandboxService = isSandbox ? (service as ExistingSandboxService) : null;

  const descriptor = useMemo(
    () => getProviderDescriptor(service.provider),
    [service.provider],
  );
  const [name, setName] = useState(service.name);
  const [apiKey, setApiKey] = useState(service.api_key || '');
  const [apiKeyChanged, setApiKeyChanged] = useState(false);
  const [baseUrl, setBaseUrl] = useState(service.base_url || '');
  const [apiVersion, setApiVersion] = useState(aiService?.api_version || '');
  const [awsAccessKeyId, setAwsAccessKeyId] = useState(aiService?.aws_access_key_id || '');
  const [awsRegion, setAwsRegion] = useState(aiService?.aws_region || '');
  const [supportsVideo, setSupportsVideo] = useState(!!aiService?.supports_video);
  const [image, setImage] = useState(sandboxService?.opensandbox_image || '');
  const [target, setTarget] = useState(sandboxService?.daytona_target || '');
  const [template, setTemplate] = useState(sandboxService?.e2b_template || '');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showWizard, setShowWizard] = useState(false);

  // Reset state when the service prop changes (different service opened).
  useEffect(() => {
    setName(service.name);
    setApiKey(service.api_key || '');
    setApiKeyChanged(false);
    setBaseUrl(service.base_url || '');
    setApiVersion(aiService?.api_version || '');
    setAwsAccessKeyId(aiService?.aws_access_key_id || '');
    setAwsRegion(aiService?.aws_region || '');
    setSupportsVideo(!!aiService?.supports_video);
    setImage(sandboxService?.opensandbox_image || '');
    setTarget(sandboxService?.daytona_target || '');
    setTemplate(sandboxService?.e2b_template || '');
    setError(null);
  }, [service.service_id]);

  const showSupportsVideo =
    kind === 'ai' && (service.provider === 'Google' || service.provider === 'GoogleCloud');
  const showApiVersion = !!descriptor?.manualFields?.includes('api_version');
  const showAwsFields = !!descriptor?.manualFields?.includes('aws_access_key_id');
  const showImage = !!descriptor?.manualFields?.includes('image');
  const showTarget = !!descriptor?.manualFields?.includes('target');
  const showTemplate = !!descriptor?.manualFields?.includes('template');
  let baseUrlLabel = 'Base URL';
  if (service.provider === 'GoogleCloud') baseUrlLabel = 'GCP Project ID';
  else if (service.provider === 'opensandbox') baseUrlLabel = 'OpenSandbox server domain';
  else if (service.provider === 'daytona') baseUrlLabel = 'Daytona API URL';
  const apiKeyLabel = API_KEY_LABELS[service.provider] ?? 'API Key';

  const handleApiKeyFocus = () => {
    if (!apiKeyChanged && apiKey.startsWith(MASKED_KEY_PREFIX)) {
      setApiKey('');
      setApiKeyChanged(true);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) {
      setError('Name is required');
      return;
    }
    setError(null);
    setSubmitting(true);
    // If the user did not touch the field, send back the masked value so
    // the backend keeps the existing key untouched.
    const resolvedApiKey =
      apiKeyChanged || !apiKey.startsWith(MASKED_KEY_PREFIX) ? apiKey : service.api_key;

    const payload: ServiceFormData | SandboxServiceFormData = isSandbox
      ? {
          name: name.trim(),
          provider: service.provider,
          api_key: resolvedApiKey,
          base_url: baseUrl,
          opensandbox_image: showImage ? image.trim() || undefined : undefined,
          daytona_target: showTarget ? target.trim() || undefined : undefined,
          e2b_template: showTemplate ? template.trim() || undefined : undefined,
        }
      : {
          name: name.trim(),
          provider: service.provider,
          model_name: aiService?.model_name || '',
          api_key: resolvedApiKey,
          base_url: baseUrl,
          api_version: apiVersion || undefined,
          supports_video: supportsVideo,
          aws_access_key_id: showAwsFields ? awsAccessKeyId.trim() || undefined : undefined,
          aws_region: showAwsFields ? awsRegion.trim() || undefined : undefined,
        };
    try {
      await onSave(payload);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save service');
    } finally {
      setSubmitting(false);
    }
  };

  const handleWizardSave = async (data: ServiceFormData | SandboxServiceFormData) => {
    // The wizard owns the full edit-model flow, so once it saves we're done.
    await onSave(data);
    setShowWizard(false);
  };

  return (
    <>
      <Modal isOpen={isOpen && !showWizard} onClose={onClose} title="Edit service">
        <form onSubmit={handleSubmit} className="space-y-4">
          {error && <Alert type="error" message={error} />}

          <div className="rounded-lg border border-gray-200 bg-gray-50 p-3 space-y-3">
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-[11px] uppercase font-semibold text-gray-500 tracking-wide">
                  Provider
                </p>
                <span
                  className={`inline-flex mt-1 text-xs font-medium px-2 py-1 rounded ${getProviderBadgeColor(
                    service.provider,
                  )}`}
                >
                  {descriptor?.label || service.provider}
                </span>
              </div>
              {!isSandbox && (
                <div className="text-right">
                  <p className="text-[11px] uppercase font-semibold text-gray-500 tracking-wide">
                    Model
                  </p>
                  <p className="text-sm font-mono text-gray-800 mt-1">
                    {aiService?.model_name}
                  </p>
                </div>
              )}
              <button
                type="button"
                onClick={() => setShowWizard(true)}
                className="text-sm font-medium text-blue-600 hover:text-blue-800 inline-flex items-center gap-1"
              >
                <Pencil className="w-3.5 h-3.5" /> {isSandbox ? 'Edit configuration' : 'Change model'}
              </button>
            </div>
          </div>

          <FormField
            id="name"
            label="Name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            helpText="The label shown in agent dropdowns and lists."
          />

          {descriptor?.apiKey !== 'none' && (
            <div>
              <label
                htmlFor="api_key"
                className="block text-sm font-medium text-gray-700 mb-2"
              >
                {apiKeyLabel}
                {descriptor?.apiKey === 'optional' && (
                  <span className="text-gray-400 font-normal"> (optional)</span>
                )}
              </label>
              <input
                id="api_key"
                name="api_key"
                type="password"
                autoComplete="off"
                data-lpignore="true"
                value={apiKey}
                onChange={(e) => {
                  setApiKey(e.target.value);
                  setApiKeyChanged(true);
                }}
                onFocus={handleApiKeyFocus}
                placeholder={descriptor.apiKeyPlaceholder}
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              />
              <p className="mt-1 text-sm text-gray-500">
                Leave the masked value to keep the existing key.
              </p>
            </div>
          )}

          {descriptor?.needsBaseUrl && (
            <FormField
              id="base_url"
              label={baseUrlLabel}
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              placeholder={descriptor.baseUrlPlaceholder}
            />
          )}

          {showApiVersion && (
            <FormField
              id="api_version"
              label={service.provider === 'GoogleCloud' ? 'Region' : 'API version'}
              value={apiVersion}
              onChange={(e) => setApiVersion(e.target.value)}
            />
          )}

          {showAwsFields && (
            <>
              <FormField
                id="aws_access_key_id"
                label="AWS Access Key ID"
                value={awsAccessKeyId}
                onChange={(e) => setAwsAccessKeyId(e.target.value)}
                placeholder="AKIA..."
                required
              />
              <FormField
                id="aws_region"
                label="AWS Region"
                value={awsRegion}
                onChange={(e) => setAwsRegion(e.target.value)}
                placeholder="us-east-1"
                required
              />
            </>
          )}

          {showImage && (
            <FormField
              id="image"
              label="Container image"
              value={image}
              onChange={(e) => setImage(e.target.value)}
              placeholder="python:3.11-slim"
              helpText="Docker image used to create sandbox containers. Leave empty to use the server default."
            />
          )}

          {showTarget && (
            <FormField
              id="target"
              label="Target"
              value={target}
              onChange={(e) => setTarget(e.target.value)}
              placeholder="us"
              helpText="Daytona target/region identifier. Leave empty to use the account default."
            />
          )}

          {showTemplate && (
            <FormField
              id="template"
              label="Template"
              value={template}
              onChange={(e) => setTemplate(e.target.value)}
              placeholder="base"
              helpText="E2B sandbox template id. Leave empty to use the default template."
            />
          )}

          {showSupportsVideo && (
            <FormCheckbox
              id="supports_video"
              label="Video analysis capable"
              checked={supportsVideo}
              onChange={(e) => setSupportsVideo(e.target.checked)}
            />
          )}

          <div className="pt-2 border-t border-gray-200">
            <FormActions
              onCancel={onClose}
              isSubmitting={submitting}
              isEditing
              submitButtonColor={kind === 'ai' ? 'blue' : 'green'}
              disabled={!name.trim()}
            />
          </div>
        </form>
      </Modal>

      {showWizard && (
        <ServiceWizard
          isOpen={showWizard}
          kind={kind}
          scope={scope}
          appId={appId}
          mode="edit-model"
          initialService={service}
          existingNames={existingNames.filter((n) => n !== service.name)}
          onClose={() => setShowWizard(false)}
          onSave={handleWizardSave}
        />
      )}
    </>
  );
}

export default CompactServiceEditor;
