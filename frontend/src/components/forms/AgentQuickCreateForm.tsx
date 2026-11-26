import { useId, useState, type FormEvent } from 'react';
import { apiService, type Agent } from '../../services/api';
import { useApiMutation } from '../../hooks/useApiMutation';
import { MESSAGES, errorMessage } from '../../constants/messages';
import { FormField, FormSelect, FormTextArea } from '../ui/FormField';

export interface AgentQuickCreateFormProps {
  readonly appId: number;
  /**
   * Called after the agent is saved. `next` is the page's choice in page mode
   * ('visual' = open the visual editor, 'form' = open the full form); modal
   * mode always reports 'visual' because the canvas connects the new agent.
   * The visual editor is the default in page mode (primary button and Enter).
   */
  readonly onCreated: (agent: Agent, next: 'form' | 'visual') => void;
  readonly onCancel: () => void;
  readonly mode: 'page' | 'modal';
}

type AgentKind = 'agent' | 'ocr_agent';

/**
 * Short form for creating an agent: only what the backend requires (name) plus
 * the fields that matter for the first run. Sends only the prompt fields that
 * match the chosen type.
 */
function AgentQuickCreateForm({ appId, onCreated, onCancel, mode }: Readonly<AgentQuickCreateFormProps>) {
  const baseId = useId();
  const mutate = useApiMutation();
  const [name, setName] = useState('');
  const [nameError, setNameError] = useState<string | null>(null);
  const [type, setType] = useState<AgentKind>('agent');
  const [description, setDescription] = useState('');
  const [systemPrompt, setSystemPrompt] = useState('');
  const [visionPrompt, setVisionPrompt] = useState('');
  const [textPrompt, setTextPrompt] = useState('');
  const [submitting, setSubmitting] = useState(false);

  async function save(next: 'form' | 'visual') {
    if (submitting) return;
    const trimmedName = name.trim();
    if (!trimmedName) {
      setNameError('Name is required');
      return;
    }
    const payload =
      type === 'ocr_agent'
        ? {
            name: trimmedName,
            type,
            description: description.trim(),
            vision_system_prompt: visionPrompt.trim(),
            text_system_prompt: textPrompt.trim(),
          }
        : {
            name: trimmedName,
            type,
            description: description.trim(),
            system_prompt: systemPrompt.trim(),
          };

    setSubmitting(true);
    const agent = await mutate<Agent>(() => apiService.createAgent(appId, 0, payload), {
      loading: MESSAGES.CREATING('agent'),
      success: MESSAGES.CREATED('agent'),
      error: (err) => errorMessage(err, MESSAGES.SAVE_FAILED('agent')),
    });
    setSubmitting(false);
    if (agent === undefined) return;
    onCreated(agent, next);
  }

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    // Enter submits: in page mode the primary action is the visual editor (modal mode always opens the canvas).
    void save('visual');
  };

  const isOcr = type === 'ocr_agent';

  return (
    <form onSubmit={handleSubmit} className="space-y-4" noValidate>
      <FormField
        label="Name"
        id={`${baseId}-name`}
        value={name}
        onChange={(event) => {
          setName(event.target.value);
          if (nameError) setNameError(null);
        }}
        placeholder="Enter agent name"
        disabled={submitting}
        required
        error={nameError ?? undefined}
      />

      <FormSelect
        label="Type"
        id={`${baseId}-type`}
        value={type}
        onChange={(event) => setType(event.target.value === 'ocr_agent' ? 'ocr_agent' : 'agent')}
        options={[
          { value: 'agent', label: 'Agent' },
          { value: 'ocr_agent', label: 'OCR agent' },
        ]}
        disabled={submitting}
        required
      />

      <FormTextArea
        label="Description"
        id={`${baseId}-description`}
        value={description}
        onChange={(event) => setDescription(event.target.value)}
        placeholder="What this agent does"
        disabled={submitting}
        helpText="Recommended — other agents read this when they use it as a tool"
        rows={2}
      />

      {isOcr ? (
        <>
          <FormTextArea
            label="Vision prompt"
            id={`${baseId}-vision-prompt`}
            value={visionPrompt}
            onChange={(event) => setVisionPrompt(event.target.value)}
            disabled={submitting}
            helpText="Recommended"
            rows={3}
          />
          <FormTextArea
            label="Text prompt"
            id={`${baseId}-text-prompt`}
            value={textPrompt}
            onChange={(event) => setTextPrompt(event.target.value)}
            disabled={submitting}
            helpText="Recommended"
            rows={3}
          />
        </>
      ) : (
        <FormTextArea
          label="System prompt"
          id={`${baseId}-system-prompt`}
          value={systemPrompt}
          onChange={(event) => setSystemPrompt(event.target.value)}
          disabled={submitting}
          helpText="Recommended"
          rows={4}
        />
      )}

      <div className="flex flex-wrap items-center justify-end gap-3 border-t border-gray-200 pt-4 dark:border-gray-700">
        <button
          type="button"
          onClick={onCancel}
          disabled={submitting}
          className="rounded-lg border border-gray-300 px-4 py-2 text-gray-700 transition-colors hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-gray-600 dark:text-gray-200 dark:hover:bg-gray-700"
        >
          Cancel
        </button>
        {mode === 'page' ? (
          <>
            <button
              type="button"
              onClick={() => void save('form')}
              disabled={submitting}
              className="rounded-lg border border-blue-600 px-4 py-2 text-blue-700 transition-colors hover:bg-blue-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-blue-500 dark:text-blue-300 dark:hover:bg-blue-900/30"
            >
              Continue in form
            </button>
            <button
              type="submit"
              disabled={submitting}
              className="rounded-lg bg-blue-600 px-4 py-2 text-white transition-colors hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {submitting ? 'Saving...' : 'Continue in visual editor'}
            </button>
          </>
        ) : (
          <button
            type="submit"
            disabled={submitting}
            className="rounded-lg bg-blue-600 px-6 py-2 text-white transition-colors hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {submitting ? 'Saving...' : 'Create'}
          </button>
        )}
      </div>
    </form>
  );
}

export default AgentQuickCreateForm;
