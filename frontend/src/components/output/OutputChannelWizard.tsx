import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import { MessageSquare, Webhook } from 'lucide-react';
import { apiService, type OutputContentMode, type OutputDestination } from '../../services/api';
import Modal from '../ui/Modal';
import Alert from '../ui/Alert';
import { StepperHeader, StepperNavigation } from '../ui/Stepper';
import { ButtonCard } from '../ui/ButtonCard';
import { FormField, FormSelect } from '../ui/FormField';
import {
  buildChannelPayload, contentModeLabels, initialChannelForm, validateChannelConfiguration, validateChannelIdentity,
  type ChannelFieldErrors,
  type AuthMode, type OutputChannelForm, type ProviderKey,
} from './outputChannelForm';

function getChannelUrlLabel(provider: ProviderKey, isEditing: boolean, t: TFunction<'common'>): string {
  if (provider === 'webhook') return t('outputChannelWizard.fields.endpointUrl');
  if (isEditing) return t('outputChannelWizard.fields.newTeamsUrl');
  return t('outputChannelWizard.fields.teamsUrl');
}

function getChannelUrlHelpText(provider: ProviderKey, isEditing: boolean, t: TFunction<'common'>): string {
  if (provider === 'webhook') return t('outputChannelWizard.help.endpointUrl');
  if (isEditing) return t('outputChannelWizard.help.newTeamsUrl');
  return t('outputChannelWizard.help.teamsUrl');
}

function getCredentialLabel(authMode: AuthMode, t: TFunction<'common'>): string {
  return authMode === 'hmac_sha256'
    ? t('outputChannelWizard.fields.hmacCredential')
    : t('outputDestinationsPage.authentication.bearer');
}

function getCredentialHelpText(destination: OutputDestination | null, authMode: AuthMode, t: TFunction<'common'>): string | undefined {
  if (!destination?.has_credentials || destination.public_config.auth_mode !== authMode) return undefined;
  return t('outputChannelWizard.help.credential');
}

interface OutputChannelWizardProps {
  isOpen: boolean;
  appId: number;
  destination: OutputDestination | null;
  destinations: OutputDestination[];
  onClose: () => void;
  onSaved: (destination: OutputDestination) => void;
}

export default function OutputChannelWizard({ isOpen, appId, destination, destinations, onClose, onSaved }: Readonly<OutputChannelWizardProps>) {
  const { t } = useTranslation('common');
  const steps = [
    { id: 'channel', label: t('outputChannelWizard.steps.channel') },
    { id: 'configuration', label: t('outputChannelWizard.steps.configuration') },
    { id: 'review', label: t('outputChannelWizard.steps.review') },
  ];
  const authLabels: Record<AuthMode, string> = {
    hmac_sha256: t('outputDestinationsPage.authentication.hmac'),
    bearer: t('outputDestinationsPage.authentication.bearer'),
    none: t('outputDestinationsPage.authentication.none'),
  };
  const [form, setForm] = useState<OutputChannelForm>(() => initialChannelForm(null));
  const [currentStep, setCurrentStep] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const submittingRef = useRef(false);
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<ChannelFieldErrors>({});
  const stepTitleRef = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    if (!isOpen) return;
    setForm(initialChannelForm(destination));
    setCurrentStep(0);
    setError(null);
    setFieldErrors({});
  }, [isOpen, destination]);

  useEffect(() => {
    if (isOpen) stepTitleRef.current?.focus();
  }, [currentStep, isOpen]);

  const update = (patch: Partial<OutputChannelForm>) => {
    setForm((previous) => ({ ...previous, ...patch }));
    setError(null);
    setFieldErrors((previous) => {
      const nextErrors = { ...previous };
      if ('name' in patch) delete nextErrors.name;
      if ('contentMode' in patch) delete nextErrors.contentMode;
      if ('url' in patch || 'provider' in patch) delete nextErrors.url;
      if ('credential' in patch || 'authMode' in patch || 'provider' in patch) delete nextErrors.credential;
      return nextErrors;
    });
  };
  const close = () => { if (!submittingRef.current) onClose(); };
  const moveBack = (step: number) => {
    if (submittingRef.current) return;
    setError(null);
    setFieldErrors({});
    setCurrentStep(step);
  };

  const next = async () => {
    if (submittingRef.current) return;
    const identityError = validateChannelIdentity(form, destinations, destination, t);
    if (identityError) {
      setError(null);
      setFieldErrors(identityError);
      if (currentStep !== 0) setCurrentStep(0);
      return;
    }
    if (currentStep === 0) {
      setError(null);
      setFieldErrors({});
      setCurrentStep(1);
      return;
    }
    const configurationError = validateChannelConfiguration(form, destination, t);
    if (configurationError) {
      setError(null);
      setFieldErrors(configurationError);
      if (currentStep === 2) setCurrentStep(1);
      return;
    }
    setFieldErrors({});
    if (currentStep < 2) {
      setError(null);
      setCurrentStep(currentStep + 1);
      return;
    }
    submittingRef.current = true;
    setSubmitting(true);
    setError(null);
    try {
      const payload = buildChannelPayload(form, destination);
      const saved = destination
        ? await apiService.updateOutputDestination(appId, destination.id, payload)
        : await apiService.createOutputDestination(appId, {
          ...payload, provider_key: form.provider, webhook_url: form.url.trim(),
        });
      onSaved(saved);
      onClose();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : t('outputChannelWizard.saveFailed'));
    } finally {
      submittingRef.current = false;
      setSubmitting(false);
    }
  };

  const channelUrlLabel = getChannelUrlLabel(form.provider, Boolean(destination), t);
  const channelUrlHelpText = getChannelUrlHelpText(form.provider, Boolean(destination), t);
  const credentialLabel = getCredentialLabel(form.authMode, t);
  const credentialHelpText = getCredentialHelpText(destination, form.authMode, t);
  let nextLabel = t('outputChannelWizard.actions.next');
  if (currentStep === 2) {
    nextLabel = destination
      ? t('outputChannelWizard.actions.saveChanges')
      : t('outputChannelWizard.actions.create');
  }
  let reviewUrl = t('outputChannelWizard.review.urlRetained');
  if (form.url.trim()) {
    reviewUrl = t(destination
      ? 'outputChannelWizard.review.urlWillRenew'
      : 'outputChannelWizard.review.urlConfigured', {
      host: new URL(form.url.trim()).hostname,
    });
  }
  let credentialReview = t('outputChannelWizard.review.credentialRetained');
  if (form.credential.trim()) {
    credentialReview = t(destination
      ? 'outputChannelWizard.review.credentialRenewed'
      : 'outputChannelWizard.review.credentialConfigured');
  }
  const attachmentsReview = form.includeAttachments
    ? t('outputChannelWizard.review.attachmentsIncluded')
    : t('outputChannelWizard.review.attachmentsDisabled');
  const deduplicationReview = form.receiverDeduplicates
    ? t('outputChannelWizard.review.deduplicationConfirmed')
    : t('outputChannelWizard.review.deduplicationUnconfirmed');

  return (
    <Modal isOpen={isOpen} onClose={close} title={destination
      ? t('outputChannelWizard.editTitle')
      : t('outputChannelWizard.createTitle')} size="large">
      <div className="flex min-h-[420px] flex-col">
        <StepperHeader steps={steps} currentStep={currentStep} onStepClick={moveBack} />
        <form className="flex flex-1 flex-col" onSubmit={(event) => { event.preventDefault(); void next(); }}>
          <fieldset disabled={submitting} className="min-w-0 flex-1 space-y-5 px-2 py-3">
            <h4 ref={stepTitleRef} tabIndex={-1} className="text-md font-medium text-fg dark:text-fg-dark outline-none mb-1">{steps[currentStep].label}</h4>
            {currentStep === 0 && <>
              <p className="text-sm text-fg dark:text-fg-dark">{t('outputChannelWizard.intro')}</p>
              <fieldset className="grid gap-3 sm:grid-cols-2">
                <legend className="sr-only">{t('outputChannelWizard.fields.channelType')}</legend>
                {([
                  {
                    key: 'teams_workflow',
                    label: t('outputDestinationsPage.providers.teamsWorkflow'),
                    description: t('outputChannelWizard.providers.teamsDescription'),
                    icon: MessageSquare,
                  },
                  {
                    key: 'webhook',
                    label: t('outputDestinationsPage.providers.webhook'),
                    description: t('outputChannelWizard.providers.webhookDescription'),
                    icon: Webhook,
                  },
                ] as const).map(({ key, label, description, icon: Icon }) => (
                  <ButtonCard
                    key={key}
                    variant="selectable"
                    selected={form.provider === key}
                    disabled={Boolean(destination)}
                    ariaLabel={label}
                    onClick={() => { if (form.provider !== key) update({ provider: key as ProviderKey, url: '', credential: '' }); }}
                  >
                    <div className="flex items-center gap-3">
                      <Icon className="h-6 w-6 shrink-0 text-fg dark:text-fg-dark" aria-hidden="true" />
                      <span className="text-sm font-medium text-fg dark:text-fg-dark">{label}</span>
                    </div>
                    <span className="mt-2 block text-xs text-fg-secondary dark:text-fg-secondary-dark">{description}</span>
                  </ButtonCard>
                ))}
              </fieldset>
              {destination && (
                <p className="text-xs text-fg-tertiary dark:text-fg-tertiary-dark">
                  {t('outputChannelWizard.typeLocked')}
                </p>
              )}
              <FormField
                id="channel-name"
                label={t('outputChannelWizard.fields.channelName')}
                value={form.name}
                onChange={(event) => update({ name: event.target.value })}
                maxLength={255}
                placeholder={t('outputChannelWizard.fields.channelNamePlaceholder')}
                autoComplete="off"
                error={fieldErrors.name}
              />
            </>}
            {currentStep === 1 && <>
              {(!destination || form.provider === 'teams_workflow') ? 
                <FormField
                  id="channel-url"
                  type="url"
                  label={channelUrlLabel}
                  value={form.url}
                  onChange={(event) => update({ url: event.target.value })}
                  autoComplete="off"
                  placeholder={destination
                    ? t('outputChannelWizard.fields.keepSavedUrl')
                    : 'https://…'}
                  helpText={channelUrlHelpText}
                  error={fieldErrors.url}
                /> : <Alert type="info" message={t('outputChannelWizard.help.endpointSaved')} />}
                <FormSelect
                  id="channel-content-mode"
                  label={t('outputChannelWizard.fields.contentMode')}
                  value={form.contentMode}
                  onChange={(event) => update({ contentMode: event.target.value as OutputContentMode })}
                  options={Object.entries(contentModeLabels(form.provider, t)).map(([value, label]) => ({ value, label }))}
                  helpText={t('outputChannelWizard.help.contentMode')}
                  error={fieldErrors.contentMode}
                />
              {form.provider === 'webhook' && <>
                <FormSelect
                  id="channel-auth-mode"
                  label={t('outputDestinationsPage.columns.authentication')}
                  value={form.authMode}
                  onChange={(event) => update({ authMode: event.target.value as AuthMode, credential: '' })}
                  options={Object.entries(authLabels).map(([value, label]) => ({ value, label }))}
                />
                {form.authMode !== 'none' && <FormField
                  id="channel-credential"
                  type="password"
                  label={credentialLabel}
                  value={form.credential}
                  onChange={(event) => update({ credential: event.target.value })}
                  autoComplete="new-password"
                  helpText={credentialHelpText}
                  error={fieldErrors.credential}
                />}
                <div className="grid gap-3 sm:grid-cols-2">
                  <ButtonCard
                    variant="selectable-check"
                    selected={form.includeAttachments}
                    ariaLabel={t('outputChannelWizard.fields.includeAttachments')}
                    checkboxLabel={t('outputChannelWizard.fields.includeAttachments')}
                    checkboxHelpText={t('outputChannelWizard.help.includeAttachments')}
                    onClick={() => update({ includeAttachments: !form.includeAttachments })}
                  />
                  <ButtonCard
                    variant="selectable-check"
                    selected={form.receiverDeduplicates}
                    ariaLabel={t('outputChannelWizard.fields.receiverDeduplicates')}
                    checkboxLabel={t('outputChannelWizard.fields.receiverDeduplicates')}
                    checkboxHelpText={t('outputChannelWizard.help.receiverDeduplicates')}
                    onClick={() => update({ receiverDeduplicates: !form.receiverDeduplicates })}
                  />
                </div>
              </>}
            </>}
            {currentStep === 2 && <>
              <p className="text-sm text-fg dark:text-fg-dark">
                {t(destination
                  ? 'outputChannelWizard.review.introEdit'
                  : 'outputChannelWizard.review.introCreate')}
              </p>
              <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-3 rounded-md bg-canvas-alt dark:bg-canvas-alt-dark p-4 text-sm">
                <dt className="text-fg-secondary dark:text-fg-secondary-dark">{t('outputChannelWizard.review.name')}</dt><dd className="break-words font-medium text-fg dark:text-fg-dark">{form.name.trim()}</dd>
                <dt className="text-fg-secondary dark:text-fg-secondary-dark">{t('outputChannelWizard.review.type')}</dt><dd className="text-fg dark:text-fg-dark">{form.provider === 'webhook' ? t('outputDestinationsPage.providers.webhook') : t('outputDestinationsPage.providers.teamsWorkflow')}</dd>
                <dt className="text-fg-secondary dark:text-fg-secondary-dark">{t('outputDestinationsPage.columns.content')}</dt><dd className="text-fg dark:text-fg-dark">{contentModeLabels(form.provider, t)[form.contentMode]}</dd>
                <dt className="text-fg-secondary dark:text-fg-secondary-dark">{t('outputChannelWizard.review.url')}</dt><dd className="break-all text-fg dark:text-fg-dark">{reviewUrl}</dd>
                {form.provider === 'webhook' && <>
                  <dt className="text-fg-secondary dark:text-fg-secondary-dark">{t('outputDestinationsPage.columns.authentication')}</dt><dd className="text-fg dark:text-fg-dark">{authLabels[form.authMode]}</dd>
                  {form.authMode !== 'none' && <><dt className="text-fg-secondary dark:text-fg-secondary-dark">{t('outputChannelWizard.review.credential')}</dt><dd className="text-fg dark:text-fg-dark">{credentialReview}</dd></>}
                  <dt className="text-fg-secondary dark:text-fg-secondary-dark">{t('outputDestinationsPage.columns.attachments')}</dt><dd className="text-fg dark:text-fg-dark">{attachmentsReview}</dd>
                  <dt className="text-fg-secondary dark:text-fg-secondary-dark">{t('outputChannelWizard.review.deduplication')}</dt><dd className="text-fg dark:text-fg-dark">{deduplicationReview}</dd>
                </>}
              </dl>
              <Alert type="info" message={t('outputChannelWizard.review.testAfterSave')} />
            </>}
          </fieldset>
          {error && <Alert type="error" message={error} className="mx-2 mt-3" />}
          <StepperNavigation currentStep={currentStep} totalSteps={steps.length} onNext={() => { void next(); }} onBack={() => moveBack(currentStep - 1)} onCancel={close} backLabel={t('outputChannelWizard.actions.back')} cancelLabel={t('outputChannelWizard.actions.cancel')} nextLabel={nextLabel} isSubmitting={submitting} submittingLabel={t('outputChannelWizard.actions.saving')} />
        </form>
      </div>
    </Modal>
  );
}
