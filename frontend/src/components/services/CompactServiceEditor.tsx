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
  ExistingService,
  ServiceFormData,
  ServiceKind,
  ServiceScope,
} from '../../types/services';

const MASKED_KEY_PREFIX = '****';

interface CompactServiceEditorProps {
  readonly isOpen: boolean;
  readonly kind: ServiceKind;
  readonly scope: ServiceScope;
  readonly appId?: number;
  readonly service: ExistingService;
  readonly existingNames?: readonly string[];
  readonly onClose: () => void;
  readonly onSave: (data: ServiceFormData) => Promise<void>;
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
  const descriptor = useMemo(
    () => getProviderDescriptor(service.provider),
    [service.provider],
  );
  const [name, setName] = useState(service.name);
  const [apiKey, setApiKey] = useState(service.api_key || '');
  const [apiKeyChanged, setApiKeyChanged] = useState(false);
  const [baseUrl, setBaseUrl] = useState(service.base_url || '');
  const [apiVersion, setApiVersion] = useState(service.api_version || '');
  const [supportsVideo, setSupportsVideo] = useState(!!service.supports_video);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showWizard, setShowWizard] = useState(false);

  // Reset state when the service prop changes (different service opened).
  useEffect(() => {
    setName(service.name);
    setApiKey(service.api_key || '');
    setApiKeyChanged(false);
    setBaseUrl(service.base_url || '');
    setApiVersion(service.api_version || '');
    setSupportsVideo(!!service.supports_video);
    setError(null);
  }, [service.service_id]);

  const showSupportsVideo =
    kind === 'ai' && (service.provider === 'Google' || service.provider === 'GoogleCloud');
  const showApiVersion = !!descriptor?.manualFields?.includes('api_version');
  const baseUrlLabel =
    service.provider === 'GoogleCloud' ? 'GCP Project ID' : 'Base URL';
  const apiKeyLabel =
    service.provider === 'GoogleCloud' ? 'Service Account JSON' : 'API Key';

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
    const payload: ServiceFormData = {
      name: name.trim(),
      provider: service.provider,
      model_name: service.model_name,
      // If the user did not touch the field, send back the masked value so
      // the backend keeps the existing key untouched.
      api_key:
        apiKeyChanged || !apiKey.startsWith(MASKED_KEY_PREFIX)
          ? apiKey
          : service.api_key,
      base_url: baseUrl,
      api_version: apiVersion || undefined,
      supports_video: supportsVideo,
    };
    try {
      await onSave(payload);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save service');
    } finally {
      setSubmitting(false);
    }
  };

  const handleWizardSave = async (data: ServiceFormData) => {
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
              <div className="text-right">
                <p className="text-[11px] uppercase font-semibold text-gray-500 tracking-wide">
                  Model
                </p>
                <p className="text-sm font-mono text-gray-800 mt-1">
                  {service.model_name}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setShowWizard(true)}
                className="text-sm font-medium text-blue-600 hover:text-blue-800 inline-flex items-center gap-1"
              >
                <Pencil className="w-3.5 h-3.5" /> Change model
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
