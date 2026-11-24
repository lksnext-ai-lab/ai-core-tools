import { useEffect, useState } from 'react';
import { Filter } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { apiService } from '../../services/api';
import CardApp from '../ui/CardApp';
import Alert from '../ui/Alert';
import ButtonCard from '../ui/ButtonCard';

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
  const { t } = useTranslation('common');
  const [fields, setFields] = useState<ChatFilterField[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState(false);

  const hasCandidates = toolIds.length > 0 || !!siloId;

  useEffect(() => {
    if (!hasCandidates) {
      setFields([]);
      setLoadError(false);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setLoadError(false);
    apiService
      .getAvailableChatFilterFields(appId, agentId, toolIds, siloId)
      .then((response) => {
        if (!cancelled) setFields(response.fields ?? []);
      })
      .catch((err: unknown) => {
        console.error('Failed to load available chat filter fields', err);
        if (!cancelled) {
          setFields([]);
          setLoadError(true);
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
    <CardApp
      icon={Filter}
      titulo={t('agentFormPage.chatFilters.title')}
      subtitulo={t('agentFormPage.chatFilters.description')}
    >

      {loading && <p className="text-sm text-fg dark:text-fg-dark">{t('agentFormPage.chatFilters.loading')}</p>}

      {!loading && loadError && (
        <Alert type="error" message={t('agentFormPage.chatFilters.loadFailed')} />
      )}

      {!loading && !loadError && fields.length === 0 && (
        <p className="text-sm text-fg dark:text-fg-dark">
          {t('agentFormPage.chatFilters.empty')}
        </p>
      )}

      {!loading && !loadError && fields.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {fields.map((field) => (
            <ButtonCard
              key={field.name}
              variant="selectable-check"
              selected={value.includes(field.name)}
              ariaLabel={field.name}
              checkboxLabel={field.name}
              checkboxHelpText={field.description}
              onClick={() => toggleField(field.name)}
            />
          ))}
        </div>
      )}
    </CardApp>
  );
}

export default ExposedChatFiltersSection;
