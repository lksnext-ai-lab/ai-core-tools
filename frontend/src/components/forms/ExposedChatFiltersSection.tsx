import { useEffect, useState } from 'react';
import { Filter } from 'lucide-react';
import { apiService } from '../../services/api';

interface ChatFilterField {
  name: string;
  type: string;
  description?: string;
}

export interface ExposedChatFiltersSectionProps {
  readonly appId: number;
  readonly agentId: number;
  readonly toolIds: number[];
  readonly siloId?: number | null;
  readonly value: string[];
  readonly onChange: (fields: string[]) => void;
}

/**
 * Designer-facing picker: choose which metadata fields — declared across this agent's
 * currently-selected subagents (tool_ids) and/or its own silo — are exposed as
 * end-user chat-time dropdown filters. Candidates are recomputed live as the form's
 * tool/silo selection changes, even before the agent is saved (agentId may be 0/new).
 * Renders nothing when there are no candidate fields to expose.
 */
function ExposedChatFiltersSection({
  appId,
  agentId,
  toolIds,
  siloId,
  value,
  onChange,
}: ExposedChatFiltersSectionProps) {
  const [fields, setFields] = useState<ChatFilterField[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const hasCandidates = toolIds.length > 0 || !!siloId;

  useEffect(() => {
    if (!hasCandidates) {
      setFields([]);
      setError(null);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);
    apiService
      .getAvailableChatFilterFields(appId, agentId, toolIds, siloId)
      .then((response) => {
        if (!cancelled) setFields(response.fields ?? []);
      })
      .catch((err: unknown) => {
        console.error('Failed to load available chat filter fields', err);
        if (!cancelled) {
          setFields([]);
          setError('Could not load available filter fields.');
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [appId, agentId, toolIds, siloId]);

  if (!hasCandidates) return null;

  const toggleField = (name: string) => {
    onChange(value.includes(name) ? value.filter((f) => f !== name) : [...value, name]);
  };

  return (
    <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-8">
      <div className="flex items-center mb-6">
        <div className="w-10 h-10 bg-indigo-100 rounded-xl flex items-center justify-center mr-4">
          <Filter className="w-5 h-5 text-indigo-600" aria-hidden="true" />
        </div>
        <div>
          <h3 className="text-xl font-semibold text-gray-900">Chat filters</h3>
          <p className="text-sm text-gray-500">
            Metadata fields end users can filter on when chatting with this agent
          </p>
        </div>
      </div>

      {loading && <p className="text-sm text-gray-500">Loading available fields…</p>}

      {!loading && error && (
        <p role="alert" className="text-sm text-red-600">
          {error}
        </p>
      )}

      {!loading && !error && fields.length === 0 && (
        <p className="text-sm text-gray-500">No metadata fields available from the selected tools/silo yet.</p>
      )}

      {!loading && !error && fields.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {fields.map((field) => (
            <div key={field.name} className="flex items-center p-3 bg-gray-50 rounded-xl">
              <input
                id={`exposed_chat_filter_${field.name}`}
                type="checkbox"
                checked={value.includes(field.name)}
                onChange={() => toggleField(field.name)}
                className="w-4 h-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
              />
              <label
                htmlFor={`exposed_chat_filter_${field.name}`}
                className="ml-3 text-sm font-medium text-gray-900"
              >
                {field.name}
                {field.description && (
                  <span className="block text-xs font-normal text-gray-500">{field.description}</span>
                )}
              </label>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default ExposedChatFiltersSection;
