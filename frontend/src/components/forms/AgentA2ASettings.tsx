import { useCallback, useId, useRef, useState } from 'react';
import { ArrowUpRight, Copy, Plus, Trash2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { TagInput } from '../ui/TagInput';
import Alert from '../ui/Alert';
import CardApp from '../ui/CardApp';
import FormField, { FormTextArea } from '../ui/FormField';
import ButtonApp from '../ui/ButtonApp';

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
  copyLabel,
  onCopy,
}: {
  readonly id: string;
  readonly label: string;
  readonly value: string | null;
  readonly hint: string;
  readonly copyLabel: string;
  readonly onCopy: (value: string, label: string) => void;
}) {
  return (
    <div>
      <label htmlFor={id} className="block text-sm font-medium text-fg dark:text-fg-dark mb-2">
        {label}
      </label>

      {value ? (
        <div className="flex items-center gap-2">
         <FormField
            label={label}
            id={id}
            disabled
            value={value}
            onChange={() => undefined}
            className="flex-1"
          />
          <ButtonApp variant="secondary" label={copyLabel} type="button" onClick={() => onCopy(value, label)} icon={<Copy className="w-4 h-4" aria-hidden="true" />} />
        </div>
      ) : (
        
        <Alert type="warning" message={hint} className="mt-2" />
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
  const { t } = useTranslation('common');
  const [copyStatus, setCopyStatus] = useState('');
  const enableId = useId();
  const enableHintId = useId();
  const enableErrorId = useId();
  const nameId = useId();
  const nameErrorId = useId();
  const descriptionId = useId();
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
      .then(() => setCopyStatus(t('agentA2ASettings.copySucceeded', { label })))
      .catch(() => setCopyStatus(t('agentA2ASettings.copyFailed', { label })));
  }, [t]);

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
    <CardApp className="p-8 space-y-8">
      {/* aria-live region announcing copy outcomes; always mounted so updates are caught */}
      <p aria-live="polite" className="min-h-[1.25rem] text-sm text-green-700 dark:text-green-400">
        {copyStatus}
      </p>

      <div className="flex items-start gap-3">
        <FormField
          id={enableId}
          type="checkbox"
          className="mt-1"
          checked={value.a2a_enabled}
          disabled={disabled}
          ariaInvalid={!!enableError}
          ariaDescribedBy={enableError ? `${enableHintId} ${enableErrorId}` : enableHintId}
          onChange={(e) => onChange({ a2a_enabled: e.target.checked })}
        />
        <div>
          <label htmlFor={enableId} className="text-sm font-medium text-fg dark:text-fg-dark">
            {t('agentA2ASettings.exposeAgent')}
          </label>
          <p id={enableHintId} className="text-sm text-fg-secondary dark:text-fg-secondary-dark mt-1">
            {t('agentA2ASettings.exposeAgentHelp')}
          </p>
          <FieldError id={enableErrorId} message={enableError} />
        </div>
      </div>

      <fieldset disabled={disabled} aria-describedby={visibilityError ? visibilityErrorId : undefined}>
        <legend className="text-sm font-medium text-fg dark:text-fg-dark mb-2">{t('agentA2ASettings.visibility')}</legend>
        <div className="space-y-2">
          <FormField
            id={`${visibilityErrorId}-public`}
            type="radio"
            name="a2a_card_visibility"
            value="public"
            label={t('agentA2ASettings.publicVisibility')}
            labelClassName="text-sm text-fg-secondary dark:text-fg-secondary-dark"
            className="flex items-center gap-2"
            checked={value.a2a_card_visibility === 'public'}
            disabled={disabled}
            onChange={() => onChange({ a2a_card_visibility: 'public' })}
          />
          <FormField
            id={`${visibilityErrorId}-api-key`}
            type="radio"
            name="a2a_card_visibility"
            value="api_key"
            label={t('agentA2ASettings.apiKeyVisibility')}
            labelClassName="text-sm text-fg-secondary dark:text-fg-secondary-dark"
            className="flex items-center gap-2"
            checked={value.a2a_card_visibility === 'api_key'}
            disabled={disabled}
            onChange={() => onChange({ a2a_card_visibility: 'api_key' })}
          />
        </div>
        <FieldError id={visibilityErrorId} message={visibilityError} />
      </fieldset>

      <div>
        <FormField
          label={t('agentA2ASettings.nameOverride')}
          id={nameId}
          type="text"
          value={value.a2a_name_override ?? ''}
          disabled={disabled}
          maxLength={MAX_NAME_LENGTH}
          helpText={t('agentA2ASettings.charactersCount', { count: (value.a2a_name_override ?? '').length, max: MAX_NAME_LENGTH })}
          helpTextAriaLive="polite"
          ariaInvalid={!!nameError}
          ariaDescribedBy={nameError ? nameErrorId : undefined}
          onChange={(e) => onChange({ a2a_name_override: e.target.value || null })}
          placeholder={t('agentA2ASettings.namePlaceholder')}
        />
        <FieldError id={nameErrorId} message={nameError} />
      </div>

      <div>
        <FormTextArea
          label={t('agentA2ASettings.descriptionOverride')}
          id={descriptionId}
          value={value.a2a_description_override ?? ''}
          disabled={disabled}
          maxLength={MAX_DESCRIPTION_LENGTH}
          helpText={t('agentA2ASettings.charactersCount', { count: (value.a2a_description_override ?? '').length, max: MAX_DESCRIPTION_LENGTH })}
          helpTextAriaLive="polite"
          rows={3}
          ariaInvalid={!!descriptionError}
          ariaDescribedBy={descriptionError ? descriptionErrorId : undefined}
          onChange={(e) => onChange({ a2a_description_override: e.target.value || null })}
          placeholder={t('agentA2ASettings.descriptionPlaceholder')}
        />
        <FieldError id={descriptionErrorId} message={descriptionError} />
      </div>

      <div>
        <label htmlFor="a2a-skill-tags" className="block text-sm font-medium text-fg dark:text-fg-dark mb-2">
          {t('agentA2ASettings.skillTags')}
        </label>
        <TagInput
          id="a2a-skill-tags"
          tags={value.a2a_skill_tags}
          onChange={handleSkillTagsChange}
          maxTags={MAX_SKILL_TAGS}
          disabled={disabled}
          placeholder={t('agentA2ASettings.skillTagsPlaceholder')}
        />
        <p className="text-xs text-fg-tertiary dark:text-fg-tertiary-dark mt-1">{t('agentA2ASettings.skillTagLimit', { max: MAX_SKILL_TAG_LENGTH })}</p>
        <FieldError id={skillTagsErrorId} message={skillTagsError} />
      </div>

      <div>
        <span className="block text-sm font-medium text-fg dark:text-fg-dark mb-3">{t('agentA2ASettings.examples')}</span>
        <p className="text-xs text-fg-secondary dark:text-fg-secondary-dark mb-3">
          {t('agentA2ASettings.examplesHelp', { maxExamples: MAX_EXAMPLES, maxCharacters: MAX_EXAMPLE_LENGTH })}
        </p>
        <div className="space-y-3">
          {value.a2a_examples.map((example, idx) => (
            <div key={`${exampleKeyPrefix}-${idx}`} className="flex items-start gap-2">
              <div className="flex-1">
                <FormTextArea
                  ref={(el) => {
                    exampleTextareaRefs.current[idx] = el;
                  }}
                  id={`${exampleKeyPrefix}-example-${idx}`}
                  label={t('agentA2ASettings.exampleLabel', { number: idx + 1 })}
                  labelClassName="sr-only"
                  ariaLabel={t('agentA2ASettings.exampleLabel', { number: idx + 1 })}
                  value={example}
                  disabled={disabled}
                  maxLength={MAX_EXAMPLE_LENGTH}
                  helpText={t('agentA2ASettings.charactersCount', { count: example.length, max: MAX_EXAMPLE_LENGTH })}
                  helpTextAriaLive="polite"
                  rows={2}
                  onChange={(e) => updateExample(idx, e.target.value)}
                  placeholder={t('agentA2ASettings.examplePlaceholder')}
                />
              </div>
              <button
                type="button"
                disabled={disabled}
                ref={(el) => {
                  exampleRemoveButtonRefs.current[idx] = el;
                }}
                onClick={() => removeExample(idx)}
                aria-label={t('agentA2ASettings.removeExample', { number: idx + 1 })}
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
            className="px-4 py-2 rounded-md text-sm border border-ink bg-surface text-fg hover:bg-surface-hover dark:border-ink-dark dark:bg-surface-dark dark:text-fg-dark dark:hover:bg-surface-hover-dark inline-flex cursor-pointer items-center justify-center gap-2 font-display font-normal tracking-[-0.02em] transition-colors disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Plus className="w-4 h-4 mr-1" aria-hidden="true" />
            {t('agentA2ASettings.addExample')}
          </button>
        </div>
        <FieldError id={examplesErrorId} message={examplesError} />
      </div>

      <div className="space-y-4 border-t border-gray-200 dark:border-gray-700 pt-6">
        <CopyableField
          id={cardUrlId}
          label={t('agentA2ASettings.cardUrl')}
          value={cardUrl}
          hint={t('agentA2ASettings.cardUrlMissingSlug')}
          copyLabel={t('agentA2ASettings.copy')}
          onCopy={handleCopy}
        />
        {!cardUrl && (
          <Link to={slugSettingsUrl} className="text-sm text-bronze  dark:text-bronze-dark inline-block">
            {t('agentA2ASettings.setSlugLink')}<ArrowUpRight className="w-4 h-4 inline-block ml-1" aria-hidden="true" />
          </Link>
        )}

        <CopyableField
          id={rpcUrlId}
          label={t('agentA2ASettings.rpcUrl')}
          value={rpcUrl}
          hint={t('agentA2ASettings.rpcUrlMissingSlug')}
          copyLabel={t('agentA2ASettings.copy')}
          onCopy={handleCopy}
        />
      </div>

      <Alert
        type="info"
        title={t('agentA2ASettings.apiKeyRequired')}
        className="my-1"
        message={(
          <>
            {t('agentA2ASettings.apiKeyInstructions')}{' '}
            <Link to={apiKeysSettingsUrl} className="inline-block underline">
              {t('agentA2ASettings.apiKeysSettings')}
            </Link>.
          </>
        )}
      />


    </CardApp>
  );
}

export default AgentA2ASettings;
