import { CheckCircle2, Loader2, Plug, XCircle } from 'lucide-react';
import { FormCheckbox } from '../../../ui/FormField';
import Alert from '../../../ui/Alert';
import { getProviderBadgeColor } from '../../../ui/providerBadges';
import { getProviderDescriptor } from '../providers';
import type {
  ProviderModelInfo,
  ServiceKind,
} from '../../../../types/services';
import type { CredentialsState } from './CredentialsStep';
import type { TestConnectionResult } from '../../serviceApi';

interface ConfirmStepProps {
  readonly kind: ServiceKind;
  readonly provider: string;
  readonly model: ProviderModelInfo | null;
  readonly manualModelName: string;
  readonly autoName: string;
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
  autoName,
  credentials,
  supportsVideo,
  onSupportsVideoChange,
  onTest,
  testing,
  testResult,
}: Readonly<ConfirmStepProps>) {
  const descriptor = getProviderDescriptor(provider);
  const isManual = !descriptor?.supportsModelListing;
  const modelLabel = isManual ? manualModelName : model?.display_name || '—';
  const modelId = isManual ? manualModelName : model?.id || '';

  const showSupportsVideo =
    kind === 'ai' && (provider === 'Google' || provider === 'GoogleCloud');

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-base font-semibold text-gray-900">Review and save</h3>
        <p className="text-sm text-gray-600 mt-1">
          The service will be saved with the following configuration.
        </p>
      </div>

      <div className="border border-gray-200 rounded-lg divide-y divide-gray-200 bg-white">
        <Row label="Name">
          <span className="text-sm text-gray-900 font-medium">{autoName}</span>
          <p className="text-xs text-gray-500 mt-0.5">
            Auto-generated. You can rename it later from the service editor.
          </p>
        </Row>

        <Row label="Provider">
          <span
            className={`inline-flex text-xs font-medium px-2 py-1 rounded ${getProviderBadgeColor(
              provider,
            )}`}
          >
            {descriptor?.label || provider}
          </span>
        </Row>

        <Row label="Model">
          <div>
            <p className="text-sm font-medium text-gray-900">{modelLabel}</p>
            {modelId && modelId !== modelLabel && (
              <p className="text-xs font-mono text-gray-500 mt-0.5">{modelId}</p>
            )}
            {model && <ModelCapabilityChips model={model} />}
          </div>
        </Row>

        {credentials.base_url && (
          <Row label={provider === 'GoogleCloud' ? 'Project ID' : 'Endpoint'}>
            <span className="text-sm text-gray-700 font-mono break-all">
              {credentials.base_url}
            </span>
          </Row>
        )}

        {credentials.api_version && (
          <Row label={provider === 'GoogleCloud' ? 'Region' : 'API version'}>
            <span className="text-sm text-gray-700 font-mono">
              {credentials.api_version}
            </span>
          </Row>
        )}

        {descriptor?.apiKey !== 'none' && credentials.api_key && (
          <Row label="API key">
            <span className="text-sm font-mono text-gray-700">
              {maskKey(credentials.api_key)}
            </span>
          </Row>
        )}
      </div>

      {showSupportsVideo && (
        <FormCheckbox
          id="supports_video"
          label="Video analysis capable"
          checked={supportsVideo}
          onChange={(e) => onSupportsVideoChange(e.target.checked)}
          helpText="Enable if the model can analyse video frames (Gemini 1.5+, Vertex)."
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
          title="Deprecated model"
          message="The provider lists this model as deprecated. Consider choosing a newer alternative."
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
  return (
    <div className="border border-gray-200 rounded-lg p-3 bg-gray-50 space-y-2">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-sm font-medium text-gray-900">Test connection</p>
          <p className="text-xs text-gray-500">
            Make a small request against the provider with these credentials
            to verify everything is set up correctly.
          </p>
        </div>
        <button
          type="button"
          onClick={() => void onTest()}
          disabled={testing}
          className={`px-3 py-1.5 text-xs font-medium rounded-md border inline-flex items-center gap-1.5 transition-colors ${
            testing
              ? 'bg-gray-100 text-gray-400 border-gray-200 cursor-not-allowed'
              : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50'
          }`}
        >
          {testing ? (
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
          ) : (
            <Plug className="w-3.5 h-3.5" />
          )}
          {testing ? 'Testing...' : 'Run test'}
        </button>
      </div>

      {result && (
        <div
          className={`rounded-md border p-2.5 text-sm flex items-start gap-2 ${
            result.status === 'success'
              ? 'bg-green-50 border-green-200 text-green-800'
              : 'bg-red-50 border-red-200 text-red-800'
          }`}
        >
          <span className="flex-shrink-0 pt-0.5">
            {result.status === 'success' ? (
              <CheckCircle2 className="w-4 h-4 text-green-500" />
            ) : (
              <XCircle className="w-4 h-4 text-red-500" />
            )}
          </span>
          <div className="flex-1 min-w-0">
            <p className="font-medium">
              {result.status === 'success' ? 'Connection successful' : 'Connection failed'}
            </p>
            <p className="mt-0.5 text-xs leading-relaxed break-words">
              {result.message}
            </p>
            {result.response && (
              <p className="mt-1 text-xs font-mono text-gray-600 break-words">
                {result.response.length > 200
                  ? `${result.response.slice(0, 200)}…`
                  : result.response}
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function Row({ label, children }: { readonly label: string; readonly children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-3 gap-3 px-4 py-3">
      <dt className="text-xs uppercase tracking-wide text-gray-500 font-semibold pt-0.5">
        {label}
      </dt>
      <dd className="col-span-2">{children}</dd>
    </div>
  );
}

function ModelCapabilityChips({ model }: { readonly model: ProviderModelInfo }) {
  const c = model.capabilities;
  const chips: string[] = [];
  if (c.chat) chips.push('Chat');
  if (c.vision) chips.push('Vision');
  if (c.audio) chips.push('Audio');
  if (c.reasoning) chips.push('Reasoning');
  if (c.function_calling) chips.push('Tools');
  if (c.embedding) chips.push('Embedding');
  if (chips.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-1 mt-1.5">
      {chips.map((c) => (
        <span
          key={c}
          className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-gray-100 text-gray-700"
        >
          {c}
        </span>
      ))}
    </div>
  );
}

function maskKey(key: string): string {
  if (!key) return '—';
  if (key.length <= 4) return '****';
  return `****${key.slice(-4)}`;
}

export default ConfirmStep;
