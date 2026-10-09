import { useState } from 'react';
import { CheckCircle2, Loader2, Plug, XCircle } from 'lucide-react';
import Modal from '../ui/Modal';
import { apiService } from '../../services/api';
import type {
  SystemOneConnectionResult,
  SystemOneServiceDetail,
  SystemOneServicePayload,
} from '../../types/systemOne';

const DEFAULT_MODEL = 'nimble-latest';
const MAX_CONCURRENCY = 64;

interface SystemOneServiceModalProps {
  readonly isOpen: boolean;
  readonly appId: number;
  /** null = creating a new service. */
  readonly service: SystemOneServiceDetail | null;
  readonly onClose: () => void;
  readonly onSave: (payload: SystemOneServicePayload) => Promise<void> | void;
}

const inputClass =
  'w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500';

function limitsSummary(limits: Record<string, number> | null): string | null {
  if (!limits) return null;
  const parts: string[] = [];
  if (limits.max_concurrent_requests != null) parts.push(`${limits.max_concurrent_requests} concurrent requests`);
  if (limits.max_questions != null) parts.push(`${limits.max_questions} questions per call`);
  if (limits.max_prompt_tokens != null) parts.push(`${limits.max_prompt_tokens} tokens per question`);
  return parts.length ? parts.join(' · ') : null;
}

function SystemOneServiceModal({ isOpen, appId, service, onClose, onSave }: SystemOneServiceModalProps) {
  const isEdit = service !== null && service.service_id !== 0;
  const [name, setName] = useState(service?.name ?? '');
  const [endpoint, setEndpoint] = useState(service?.endpoint ?? '');
  const [apiKey, setApiKey] = useState(service?.api_key ?? '');
  const [model, setModel] = useState(service?.model ?? DEFAULT_MODEL);
  const [concurrency, setConcurrency] = useState<string>(service ? String(service.max_concurrency) : '');
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<SystemOneConnectionResult | null>(null);
  const [saving, setSaving] = useState(false);
  const [touched, setTouched] = useState(false);

  const models = testResult?.status === 'success' ? testResult.models : [];
  const limits = limitsSummary(testResult?.limits ?? null);

  const errors: Record<string, string> = {};
  if (!name.trim()) errors.name = 'The name is required';
  if (!/^https?:\/\/\S+$/i.test(endpoint.trim())) errors.endpoint = 'Enter a URL starting with http:// or https://';
  const parsedConcurrency = concurrency.trim() === '' ? null : Number(concurrency);
  if (parsedConcurrency !== null && (!Number.isInteger(parsedConcurrency) || parsedConcurrency < 1 || parsedConcurrency > MAX_CONCURRENCY)) {
    errors.concurrency = `Enter a whole number between 1 and ${MAX_CONCURRENCY}, or leave it empty`;
  }
  if (!model.trim()) errors.model = 'The model is required';
  const hasErrors = Object.keys(errors).length > 0;

  function payload(): SystemOneServicePayload {
    return {
      name: name.trim(),
      endpoint: endpoint.trim(),
      api_key: apiKey.trim(),
      model: model.trim(),
      max_concurrency: parsedConcurrency,
    };
  }

  async function handleTest() {
    setTouched(true);
    if (errors.endpoint) return;
    setTesting(true);
    setTestResult(null);
    try {
      const result = await apiService.testSystemOneServiceWithConfig(
        appId,
        { ...payload(), name: name.trim() || 'test' },
        isEdit ? service.service_id : undefined,
      );
      setTestResult(result);
      // Prefill the cap on a new service (never overwrite what the user typed or what an existing service has)
      if (result.suggested_max_concurrency != null && concurrency.trim() === '') {
        setConcurrency(String(result.suggested_max_concurrency));
      }
    } catch (err) {
      setTestResult({
        status: 'error',
        message: err instanceof Error ? err.message : 'Failed to test the connection',
        models: [],
        limits: null,
      });
    } finally {
      setTesting(false);
    }
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setTouched(true);
    if (hasErrors) return;
    setSaving(true);
    try {
      await onSave(payload());
    } finally {
      setSaving(false);
    }
  }

  const showError = (field: string) => (touched && errors[field] ? errors[field] : null);

  return (
    <Modal isOpen={isOpen} onClose={onClose} title={isEdit ? 'Edit System One service' : 'New System One service'} size="medium">
      <form onSubmit={(e) => void handleSubmit(e)} className="space-y-4 p-4" noValidate>
        <p className="text-sm text-gray-600">
          Connection to a System One (Nimble) server. It evaluates <strong>text only</strong>: it answers closed questions with probabilities.
        </p>

        <div>
          <label htmlFor="so-name" className="mb-1 block text-sm font-medium text-gray-700">Name</label>
          <input id="so-name" className={inputClass} value={name} onChange={(e) => setName(e.target.value)}
                 placeholder="Nimble (lab server)" aria-invalid={Boolean(showError('name'))} />
          {showError('name') && <p className="mt-1 text-xs text-red-600">{showError('name')}</p>}
        </div>

        <div>
          <label htmlFor="so-endpoint" className="mb-1 block text-sm font-medium text-gray-700">Server URL</label>
          <input id="so-endpoint" className={inputClass} value={endpoint} onChange={(e) => setEndpoint(e.target.value)}
                 placeholder="http://172.16.59.1:8100" aria-invalid={Boolean(showError('endpoint'))} />
          {showError('endpoint') && <p className="mt-1 text-xs text-red-600">{showError('endpoint')}</p>}
        </div>

        <div>
          <label htmlFor="so-token" className="mb-1 block text-sm font-medium text-gray-700">
            Token <span className="font-normal text-gray-500">(optional)</span>
          </label>
          <input id="so-token" type="password" autoComplete="off" className={inputClass} value={apiKey}
                 onChange={(e) => setApiKey(e.target.value)} placeholder="Bearer token, if the server requires one" />
          {isEdit && <p className="mt-1 text-xs text-gray-500">Leave the masked value to keep the stored token; empty it to remove it.</p>}
        </div>

        <div>
          <label htmlFor="so-model" className="mb-1 block text-sm font-medium text-gray-700">Model</label>
          {models.length > 0 ? (
            <select id="so-model" className={inputClass} value={model} onChange={(e) => setModel(e.target.value)}>
              {!models.includes(model) && <option value={model}>{model}</option>}
              {models.map((m) => <option key={m} value={m}>{m}</option>)}
            </select>
          ) : (
            <input id="so-model" className={inputClass} value={model} onChange={(e) => setModel(e.target.value)}
                   placeholder={DEFAULT_MODEL} aria-invalid={Boolean(showError('model'))} />
          )}
          <p className="mt-1 text-xs text-gray-500">
            {models.length > 0
              ? 'Models offered by the server.'
              : `${DEFAULT_MODEL} always uses the latest published model. Test the connection to list the available ones.`}
          </p>
          {showError('model') && <p className="mt-1 text-xs text-red-600">{showError('model')}</p>}
        </div>

        <div>
          <label htmlFor="so-concurrency" className="mb-1 block text-sm font-medium text-gray-700">
            Maximum concurrent requests <span className="font-normal text-gray-500">(per backend process)</span>
          </label>
          <input id="so-concurrency" type="number" min={1} max={MAX_CONCURRENCY} className={inputClass} value={concurrency}
                 onChange={(e) => setConcurrency(e.target.value)} placeholder="1" aria-invalid={Boolean(showError('concurrency'))} />
          <p className="mt-1 text-xs text-gray-500">
            The server accepts a limited number of requests at once and answers 529 above it. The backend runs several
            processes, so use the server limit divided by the number of processes.
            {testResult?.suggested_max_concurrency != null && (
              <> Suggested for this server: <strong>{testResult.suggested_max_concurrency}</strong>.</>
            )}
          </p>
          {showError('concurrency') && <p className="mt-1 text-xs text-red-600">{showError('concurrency')}</p>}
        </div>

        <div aria-live="polite">
          {testResult && (
            <div className={`rounded-lg p-3 text-sm ${testResult.status === 'success' ? 'bg-green-50 text-green-800' : 'bg-red-50 text-red-800'}`}>
              <div className="flex items-center gap-2 font-medium">
                {testResult.status === 'success' ? <CheckCircle2 className="h-4 w-4" aria-hidden="true" /> : <XCircle className="h-4 w-4" aria-hidden="true" />}
                {testResult.message}
              </div>
              {limits && <p className="mt-1 text-xs">Server limits: {limits}</p>}
            </div>
          )}
        </div>

        <div className="flex items-center justify-between pt-2">
          <button type="button" onClick={() => void handleTest()} disabled={testing}
                  className="inline-flex items-center gap-2 rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-700 hover:bg-gray-50 disabled:opacity-60">
            {testing ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Plug className="h-4 w-4" aria-hidden="true" />}
            {testing ? 'Testing...' : 'Test connection'}
          </button>
          <div className="flex gap-2">
            <button type="button" onClick={onClose} className="rounded-lg bg-gray-200 px-4 py-2 text-sm text-gray-800 hover:bg-gray-300">Cancel</button>
            <button type="submit" disabled={saving} className="rounded-lg bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700 disabled:opacity-60">
              {saving ? 'Saving...' : 'Save'}
            </button>
          </div>
        </div>
      </form>
    </Modal>
  );
}

export default SystemOneServiceModal;
