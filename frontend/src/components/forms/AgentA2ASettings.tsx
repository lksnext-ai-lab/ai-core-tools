import { useCallback, useId, useRef, useState } from 'react';
import { Copy, Info, Plus, Trash2 } from 'lucide-react';
import { Link } from 'react-router-dom';
import { TagInput } from '../ui/TagInput';

export type A2ACardVisibility = 'public' | 'api_key';

export interface AgentA2AValue {
  a2a_enabled: boolean;
  a2a_card_visibility: A2ACardVisibility;
  a2a_name_override: string | null;
  a2a_description_override: string | null;
  a2a_skill_tags: string[];
  a2a_examples: string[];
}

/** Server-side (422) validation messages keyed by a2a_* field name. */
export type AgentA2AFieldErrors = Partial<Record<keyof AgentA2AValue, string>>;

export interface AgentA2ASettingsProps {
  readonly appId: number;
  readonly value: AgentA2AValue;
  readonly onChange: (patch: Partial<AgentA2AValue>) => void;
  readonly cardUrl: string | null;
  readonly rpcUrl: string | null;
  readonly disabled: boolean;
  readonly fieldErrors?: AgentA2AFieldErrors;
}

const MAX_NAME_LENGTH = 255;
const MAX_DESCRIPTION_LENGTH = 1000;
const MAX_SKILL_TAGS = 20;
const MAX_SKILL_TAG_LENGTH = 50;
const MAX_EXAMPLES = 20;
const MAX_EXAMPLE_LENGTH = 500;

/** A single-line, role="alert" validation message rendered right below its field. */
function FieldError({ id, message }: { readonly id: string; readonly message?: string }) {
  if (!message) return null;
  return (
    <p id={id} role="alert" className="text-xs text-red-600 dark:text-red-400 mt-1">
      {message}
    </p>
  );
}

/** A read-only field with a copy-to-clipboard button; reports success/failure via `onCopy`. */
function CopyableField({
  id,
  label,
  value,
  hint,
  onCopy,
}: {
  readonly id: string;
  readonly label: string;
  readonly value: string | null;
  readonly hint: string;
  readonly onCopy: (value: string, label: string) => void;
}) {
  return (
    <div>
      <label htmlFor={id} className="block text-sm font-medium text-gray-700 dark:text-gray-200 mb-2">
        {label}
      </label>
      {value ? (
        <div className="flex items-center gap-2">
          <input
            id={id}
            type="text"
            readOnly
            value={value}
            className="flex-1 px-4 py-2 border border-gray-300 rounded-lg text-sm bg-gray-50 text-gray-700 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200 focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <button
            type="button"
            onClick={() => onCopy(value, label)}
            className="inline-flex items-center gap-1.5 px-3 py-2 text-sm font-medium rounded-lg border border-gray-300 text-gray-700 hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:border-gray-600 dark:text-gray-200 dark:hover:bg-gray-700"
          >
            <Copy className="w-4 h-4" aria-hidden="true" />
            Copy
          </button>
        </div>
      ) : (
        <p className="text-sm text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 dark:bg-amber-900/30 dark:border-amber-800 dark:text-amber-200">
          {hint}
        </p>
      )}
    </div>
  );
}

/**
 * A2A (Agent2Agent protocol) settings tab for AgentFormPage. Reads/writes the six
 * a2a_* fields on the agent through the caller's onChange; the read-only card/RPC
 * URLs are derived server-side (null when the app has no slug yet).
 */
export function AgentA2ASettings({
  appId,
  value,
  onChange,
  cardUrl,
  rpcUrl,
  disabled,
  fieldErrors,
}: AgentA2ASettingsProps) {
  const [copyStatus, setCopyStatus] = useState('');
  const enableId = useId();
  const enableHintId = useId();
  const enableErrorId = useId();
  const nameId = useId();
  const nameCounterId = useId();
  const nameErrorId = useId();
  const descriptionId = useId();
  const descriptionCounterId = useId();
  const descriptionErrorId = useId();
  const visibilityErrorId = useId();
  const skillTagsErrorId = useId();
  const examplesErrorId = useId();
  const cardUrlId = useId();
  const rpcUrlId = useId();
  const exampleKeyPrefix = useId();

  const addExampleButtonRef = useRef<HTMLButtonElement | null>(null);
  const exampleTextareaRefs = useRef<Array<HTMLTextAreaElement | null>>([]);
  const exampleRemoveButtonRefs = useRef<Array<HTMLButtonElement | null>>([]);

  const handleCopy = useCallback((text: string, label: string) => {
    navigator.clipboard
      .writeText(text)
      .then(() => setCopyStatus(`${label} copied`))
      .catch(() => setCopyStatus(`Could not copy ${label.toLowerCase()}`));
  }, []);

  const handleSkillTagsChange = useCallback(
    (tags: string[]) => {
      onChange({
        a2a_skill_tags: tags.slice(0, MAX_SKILL_TAGS).map((tag) => tag.slice(0, MAX_SKILL_TAG_LENGTH)),
      });
    },
    [onChange],
  );

  const updateExample = useCallback(
    (index: number, text: string) => {
      const next = [...value.a2a_examples];
      next[index] = text.slice(0, MAX_EXAMPLE_LENGTH);
      onChange({ a2a_examples: next });
    },
    [onChange, value.a2a_examples],
  );

  const removeExample = useCallback(
    (index: number) => {
      const next = value.a2a_examples.filter((_, i) => i !== index);
      onChange({ a2a_examples: next });
      // Keep focus inside the editor — land on the previous item (or the Add
      // button when the list becomes empty), never let focus fall back to <body>.
      requestAnimationFrame(() => {
        if (next.length === 0) {
          addExampleButtonRef.current?.focus();
          return;
        }
        const focusIndex = Math.max(0, index - 1);
        const target = exampleRemoveButtonRefs.current[focusIndex] ?? exampleTextareaRefs.current[focusIndex];
        target?.focus();
      });
    },
    [onChange, value.a2a_examples],
  );

  const addExample = useCallback(() => {
    if (value.a2a_examples.length >= MAX_EXAMPLES) return;
    const newIndex = value.a2a_examples.length;
    onChange({ a2a_examples: [...value.a2a_examples, ''] });
    requestAnimationFrame(() => {
      exampleTextareaRefs.current[newIndex]?.focus();
    });
  }, [onChange, value.a2a_examples]);

  const slugSettingsUrl = `/apps/${appId}/settings/general`;
  const apiKeysSettingsUrl = `/apps/${appId}/settings/api-keys`;

  const nameError = fieldErrors?.a2a_name_override;
  const descriptionError = fieldErrors?.a2a_description_override;
  const visibilityError = fieldErrors?.a2a_card_visibility;
  const enableError = fieldErrors?.a2a_enabled;
  const skillTagsError = fieldErrors?.a2a_skill_tags;
  const examplesError = fieldErrors?.a2a_examples;

  return (
    <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-sm border border-gray-200 dark:border-gray-700 p-8 space-y-8">
      {/* aria-live region announcing copy outcomes; always mounted so updates are caught */}
      <p aria-live="polite" className="min-h-[1.25rem] text-sm text-green-700 dark:text-green-400">
        {copyStatus}
      </p>

      <div className="flex items-start gap-3">
        <input
          id={enableId}
          type="checkbox"
          checked={value.a2a_enabled}
          disabled={disabled}
          aria-invalid={!!enableError}
          aria-describedby={enableError ? `${enableHintId} ${enableErrorId}` : enableHintId}
          onChange={(e) => onChange({ a2a_enabled: e.target.checked })}
          className="mt-1 w-5 h-5 rounded border-gray-300 text-blue-600 focus:ring-blue-500 disabled:cursor-not-allowed dark:border-gray-600 dark:bg-gray-700"
        />
        <div>
          <label htmlFor={enableId} className="text-sm font-medium text-gray-900 dark:text-gray-100">
            Expose this agent over the A2A protocol
          </label>
          <p id={enableHintId} className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            When enabled, external A2A clients can discover this agent's card and call it over JSON-RPC.
          </p>
          <FieldError id={enableErrorId} message={enableError} />
        </div>
      </div>

      <fieldset disabled={disabled} aria-describedby={visibilityError ? visibilityErrorId : undefined}>
        <legend className="text-sm font-medium text-gray-700 dark:text-gray-200 mb-2">Agent card visibility</legend>
        <div className="space-y-2">
          <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-200">
            <input
              type="radio"
              name="a2a_card_visibility"
              value="public"
              checked={value.a2a_card_visibility === 'public'}
              onChange={() => onChange({ a2a_card_visibility: 'public' })}
              className="w-4 h-4 text-blue-600 border-gray-300 focus:ring-blue-500 disabled:cursor-not-allowed dark:border-gray-600 dark:bg-gray-700"
            />
            Public card — anyone with the URL can read the agent card
          </label>
          <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-200">
            <input
              type="radio"
              name="a2a_card_visibility"
              value="api_key"
              checked={value.a2a_card_visibility === 'api_key'}
              onChange={() => onChange({ a2a_card_visibility: 'api_key' })}
              className="w-4 h-4 text-blue-600 border-gray-300 focus:ring-blue-500 disabled:cursor-not-allowed dark:border-gray-600 dark:bg-gray-700"
            />
            API key required — the card is only served to callers with a valid X-API-KEY
          </label>
        </div>
        <FieldError id={visibilityErrorId} message={visibilityError} />
      </fieldset>

      <div>
        <label htmlFor={nameId} className="block text-sm font-medium text-gray-700 dark:text-gray-200 mb-2">
          Name override
        </label>
        <input
          id={nameId}
          type="text"
          value={value.a2a_name_override ?? ''}
          disabled={disabled}
          maxLength={MAX_NAME_LENGTH}
          aria-invalid={!!nameError}
          aria-describedby={nameError ? `${nameCounterId} ${nameErrorId}` : nameCounterId}
          onChange={(e) => onChange({ a2a_name_override: e.target.value || null })}
          placeholder="Defaults to the agent's name"
          className="w-full px-4 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all disabled:cursor-not-allowed disabled:bg-gray-50 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100 dark:disabled:bg-gray-800"
        />
        <p id={nameCounterId} aria-live="polite" className="text-xs text-gray-500 dark:text-gray-400 mt-1">
          {(value.a2a_name_override ?? '').length}/{MAX_NAME_LENGTH} characters
        </p>
        <FieldError id={nameErrorId} message={nameError} />
      </div>

      <div>
        <label htmlFor={descriptionId} className="block text-sm font-medium text-gray-700 dark:text-gray-200 mb-2">
          Description override
        </label>
        <textarea
          id={descriptionId}
          value={value.a2a_description_override ?? ''}
          disabled={disabled}
          maxLength={MAX_DESCRIPTION_LENGTH}
          rows={3}
          aria-invalid={!!descriptionError}
          aria-describedby={descriptionError ? `${descriptionCounterId} ${descriptionErrorId}` : descriptionCounterId}
          onChange={(e) => onChange({ a2a_description_override: e.target.value || null })}
          placeholder="Defaults to the agent's description"
          className="w-full px-4 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all disabled:cursor-not-allowed disabled:bg-gray-50 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100 dark:disabled:bg-gray-800"
        />
        <p id={descriptionCounterId} aria-live="polite" className="text-xs text-gray-500 dark:text-gray-400 mt-1">
          {(value.a2a_description_override ?? '').length}/{MAX_DESCRIPTION_LENGTH} characters
        </p>
        <FieldError id={descriptionErrorId} message={descriptionError} />
      </div>

      <div>
        <label htmlFor="a2a-skill-tags" className="block text-sm font-medium text-gray-700 dark:text-gray-200 mb-2">
          Skill tags
        </label>
        <TagInput
          id="a2a-skill-tags"
          tags={value.a2a_skill_tags}
          onChange={handleSkillTagsChange}
          maxTags={MAX_SKILL_TAGS}
          disabled={disabled}
          placeholder="Type a tag and press Enter"
        />
        <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">Each tag is capped at {MAX_SKILL_TAG_LENGTH} characters.</p>
        <FieldError id={skillTagsErrorId} message={skillTagsError} />
      </div>

      <div>
        <span className="block text-sm font-medium text-gray-700 dark:text-gray-200 mb-3">Example prompts</span>
        <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">
          Shown to A2A callers as example tasks this agent can handle. Up to {MAX_EXAMPLES}, {MAX_EXAMPLE_LENGTH} characters each.
        </p>
        <div className="space-y-3">
          {value.a2a_examples.map((example, idx) => (
            <div key={`${exampleKeyPrefix}-${idx}`} className="flex items-start gap-2">
              <div className="flex-1">
                <textarea
                  ref={(el) => {
                    exampleTextareaRefs.current[idx] = el;
                  }}
                  value={example}
                  disabled={disabled}
                  maxLength={MAX_EXAMPLE_LENGTH}
                  rows={2}
                  onChange={(e) => updateExample(idx, e.target.value)}
                  aria-label={`Example prompt ${idx + 1}`}
                  aria-describedby={`${exampleKeyPrefix}-counter-${idx}`}
                  placeholder="Enter an example prompt..."
                  className="w-full px-4 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 transition-all disabled:cursor-not-allowed disabled:bg-gray-50 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100 dark:disabled:bg-gray-800"
                />
                <p
                  id={`${exampleKeyPrefix}-counter-${idx}`}
                  aria-live="polite"
                  className="text-xs text-gray-400 dark:text-gray-500 mt-1"
                >
                  {example.length}/{MAX_EXAMPLE_LENGTH}
                </p>
              </div>
              <button
                type="button"
                disabled={disabled}
                ref={(el) => {
                  exampleRemoveButtonRefs.current[idx] = el;
                }}
                onClick={() => removeExample(idx)}
                aria-label={`Remove example prompt ${idx + 1}`}
                className="p-2 text-red-500 hover:bg-red-50 rounded-lg transition-colors disabled:cursor-not-allowed disabled:opacity-50 dark:hover:bg-red-900/30"
              >
                <Trash2 className="w-4 h-4" aria-hidden="true" />
              </button>
            </div>
          ))}
          <button
            type="button"
            ref={addExampleButtonRef}
            disabled={disabled || value.a2a_examples.length >= MAX_EXAMPLES}
            onClick={addExample}
            className="inline-flex items-center px-3 py-1.5 text-sm font-medium text-blue-600 hover:text-blue-700 hover:bg-blue-50 rounded-lg transition-colors disabled:cursor-not-allowed disabled:opacity-50 dark:text-blue-400 dark:hover:bg-blue-900/30"
          >
            <Plus className="w-4 h-4 mr-1" aria-hidden="true" />
            Add example
          </button>
        </div>
        <FieldError id={examplesErrorId} message={examplesError} />
      </div>

      <div className="space-y-4 border-t border-gray-200 dark:border-gray-700 pt-6">
        <CopyableField
          id={cardUrlId}
          label="Card URL"
          value={cardUrl}
          hint="This app has no slug yet — set one in App Settings to generate the agent card URL."
          onCopy={handleCopy}
        />
        {!cardUrl && (
          <Link to={slugSettingsUrl} className="text-sm text-blue-600 hover:text-blue-700 dark:text-blue-400 inline-block">
            Go to App Settings to set a slug
          </Link>
        )}

        <CopyableField
          id={rpcUrlId}
          label="RPC URL"
          value={rpcUrl}
          hint="This app has no slug yet — set one in App Settings to generate the RPC URL."
          onCopy={handleCopy}
        />
      </div>

      <div className="flex items-start gap-2 text-sm text-gray-600 dark:text-gray-300 bg-gray-50 dark:bg-gray-900/40 border border-gray-200 dark:border-gray-700 rounded-lg px-3 py-3">
        <Info className="w-4 h-4 mt-0.5 shrink-0" aria-hidden="true" />
        <p>
          Callers must send an app API key in the <code>X-API-KEY</code> header. Create keys in the app's{' '}
          <Link to={apiKeysSettingsUrl} className="text-blue-600 hover:text-blue-700 dark:text-blue-400 underline">
            API Keys settings
          </Link>
          .
        </p>
      </div>
    </div>
  );
}

export default AgentA2ASettings;
