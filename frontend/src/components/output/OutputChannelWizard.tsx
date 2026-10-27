import { useEffect, useRef, useState } from 'react';
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

const steps = [
  { id: 'channel', label: 'Canal' },
  { id: 'configuration', label: 'Configuración' },
  { id: 'review', label: 'Revisión' },
];
const authLabels: Record<AuthMode, string> = { hmac_sha256: 'HMAC-SHA256', bearer: 'Bearer token', none: 'Sin autenticación' };

function getChannelUrlLabel(provider: ProviderKey, isEditing: boolean): string {
  if (provider === 'webhook') return 'URL HTTPS del endpoint';
  if (isEditing) return 'Nueva URL secreta del Workflow (opcional)';
  return 'URL del trigger de Teams';
}

function getChannelUrlHelpText(provider: ProviderKey, isEditing: boolean): string {
  if (provider === 'webhook') return 'El endpoint debe usar HTTPS y resolver únicamente a direcciones IP públicas.';
  if (isEditing) return 'Permite renovar la URL secreta del mismo Workflow. Para cambiar de Workflow o canal, crea un nuevo canal.';
  return 'La URL se guarda como credencial y no vuelve a mostrarse. Usa un trigger que acepte llamadas mediante URL.';
}

function getCredentialLabel(authMode: AuthMode): string {
  return authMode === 'hmac_sha256' ? 'Clave HMAC en Base64 (32 bytes)' : 'Bearer token';
}

function getCredentialHelpText(destination: OutputDestination | null, authMode: AuthMode): string | undefined {
  if (!destination?.has_credentials || destination.public_config.auth_mode !== authMode) return undefined;
  return 'Deja este campo vacío para conservar la credencial guardada o introduce una nueva para renovarla.';
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
    const identityError = validateChannelIdentity(form, destinations, destination);
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
    const configurationError = validateChannelConfiguration(form, destination);
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
      setError(cause instanceof Error ? cause.message : 'No se pudo guardar el canal.');
    } finally {
      submittingRef.current = false;
      setSubmitting(false);
    }
  };

  const channelUrlLabel = getChannelUrlLabel(form.provider, Boolean(destination));
  const channelUrlHelpText = getChannelUrlHelpText(form.provider, Boolean(destination));
  const credentialLabel = getCredentialLabel(form.authMode);
  const credentialHelpText = getCredentialHelpText(destination, form.authMode);

  return (
    <Modal isOpen={isOpen} onClose={close} title={destination ? 'Editar canal de salida' : 'Añadir canal de salida'} size="large">
      <div className="flex min-h-[420px] flex-col">
        <StepperHeader steps={steps} currentStep={currentStep} onStepClick={moveBack} />
        <form className="flex flex-1 flex-col" onSubmit={(event) => { event.preventDefault(); void next(); }}>
          <fieldset disabled={submitting} className="min-w-0 flex-1 space-y-5 px-2 py-3">
            <h4 ref={stepTitleRef} tabIndex={-1} className="text-md font-medium text-fg dark:text-fg-dark outline-none mb-1">{steps[currentStep].label}</h4>
            {currentStep === 0 && <>
              <p className="text-sm text-fg dark:text-fg-dark">Elige el tipo de canal y un nombre para identificarlo en las tareas programadas.</p>
              <fieldset className="grid gap-3 sm:grid-cols-2">
                <legend className="sr-only">Tipo de canal</legend>
                {([
                  { key: 'teams_workflow', label: 'Teams Workflow', description: 'Envía notificaciones a un canal de Teams.', icon: MessageSquare },
                  { key: 'webhook', label: 'Webhook HTTP', description: 'Envía resultados a un endpoint HTTPS.', icon: Webhook },
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
              {destination && <p className="text-xs text-fg-tertiary dark:text-fg-tertiary-dark">El tipo de canal se conserva. Para usar otro tipo, crea un nuevo canal.</p>}
              <FormField
                id="channel-name"
                label="Nombre del canal"
                value={form.name}
                onChange={(event) => update({ name: event.target.value })}
                maxLength={255}
                placeholder="Por ejemplo: Alertas"
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
                  placeholder={destination ? 'Déjala vacía para conservar la URL guardada' : 'https://…'}
                  helpText={channelUrlHelpText}
                  error={fieldErrors.url}
                /> : <Alert type="info" message="URL del endpoint guardada. Para cambiar el endpoint, crea un nuevo canal." />}
                <FormSelect
                  id="channel-content-mode"
                  label="Contenido de la notificación"
                  value={form.contentMode}
                  onChange={(event) => update({ contentMode: event.target.value as OutputContentMode })}
                  options={Object.entries(contentModeLabels(form.provider)).map(([value, label]) => ({ value, label }))}
                  helpText="Se aplica a todas las tareas vinculadas a este canal."
                  error={fieldErrors.contentMode}
                />
              {form.provider === 'webhook' && <>
                <FormSelect
                  id="channel-auth-mode"
                  label="Autenticación"
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
                    ariaLabel="Enviar archivos adjuntos"
                    checkboxLabel="Enviar archivos adjuntos"
                    checkboxHelpText="Incluye los archivos en la llamada al webhook mediante multipart/form-data. Desactivado: envío JSON."
                    onClick={() => update({ includeAttachments: !form.includeAttachments })}
                  />
                  <ButtonCard
                    variant="selectable-check"
                    selected={form.receiverDeduplicates}
                    ariaLabel="El receptor deduplica los eventos"
                    checkboxLabel="El receptor deduplica los eventos"
                    checkboxHelpText="Confirma que admite Idempotency-Key para permitir reintentos automáticos de resultado incierto."
                    onClick={() => update({ receiverDeduplicates: !form.receiverDeduplicates })}
                  />
                </div>
              </>}
            </>}
            {currentStep === 2 && <>
              <p className="text-sm text-fg dark:text-fg-dark">Revisa la configuración antes de {destination ? 'guardar los cambios' : 'crear el canal'}.</p>
              <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-3 rounded-md bg-canvas-alt dark:bg-canvas-alt-dark p-4 text-sm">
                <dt className="text-fg-secondary dark:text-fg-secondary-dark">Nombre</dt><dd className="break-words font-medium text-fg dark:text-fg-dark">{form.name.trim()}</dd>
                <dt className="text-fg-secondary dark:text-fg-secondary-dark">Tipo</dt><dd className="text-fg dark:text-fg-dark">{form.provider === 'webhook' ? 'Webhook HTTP' : 'Teams Workflow'}</dd>
                <dt className="text-fg-secondary dark:text-fg-secondary-dark">Contenido</dt><dd className="text-fg dark:text-fg-dark">{contentModeLabels(form.provider)[form.contentMode]}</dd>
                <dt className="text-fg-secondary dark:text-fg-secondary-dark">URL</dt><dd className="break-all text-fg dark:text-fg-dark">{form.url.trim() ? `${new URL(form.url.trim()).hostname} · ${destination ? 'Se renovará la URL secreta' : 'URL configurada'}` : 'Se conserva la URL guardada'}</dd>
                {form.provider === 'webhook' && <>
                  <dt className="text-fg-secondary dark:text-fg-secondary-dark">Autenticación</dt><dd className="text-fg dark:text-fg-dark">{authLabels[form.authMode]}</dd>
                  {form.authMode !== 'none' && <><dt className="text-fg-secondary dark:text-fg-secondary-dark">Credencial</dt><dd className="text-fg dark:text-fg-dark">{form.credential.trim() ? destination ? 'Se guardará una nueva credencial' : 'Configurada' : 'Se conserva la credencial guardada'}</dd></>}
                  <dt className="text-fg-secondary dark:text-fg-secondary-dark">Adjuntos</dt><dd className="text-fg dark:text-fg-dark">{form.includeAttachments ? 'Incluidos como archivos' : 'Desactivados'}</dd>
                  <dt className="text-fg-secondary dark:text-fg-secondary-dark">Deduplicación</dt><dd className="text-fg dark:text-fg-dark">{form.receiverDeduplicates ? 'Confirmada por el receptor' : 'Sin confirmar'}</dd>
                </>}
              </dl>
              <Alert type="info" message="Tras guardar, podrás probar el destino desde el menú de acciones del listado." />
            </>}
          </fieldset>
          {error && <Alert type="error" message={error} className="mx-2 mt-3" />}
          <StepperNavigation currentStep={currentStep} totalSteps={steps.length} onNext={() => { void next(); }} onBack={() => moveBack(currentStep - 1)} onCancel={close} backLabel="Atrás" cancelLabel="Cancelar" nextLabel={currentStep === 2 ? destination ? 'Guardar cambios' : 'Crear canal' : 'Siguiente'} isSubmitting={submitting} submittingLabel="Guardando…" />
        </form>
      </div>
    </Modal>
  );
}
