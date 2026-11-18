import { useEffect, useRef, useState } from 'react';
import { MessageSquare, Webhook } from 'lucide-react';
import { apiService, type OutputContentMode, type OutputDestination } from '../../services/api';
import Modal from '../ui/Modal';
import { StepperHeader, StepperNavigation } from '../ui/Stepper';
import {
  buildChannelPayload, contentModeLabels, initialChannelForm, validateChannelConfiguration, validateChannelIdentity,
  type AuthMode, type OutputChannelForm, type ProviderKey,
} from './outputChannelForm';

const steps = [
  { id: 'channel', label: 'Canal' },
  { id: 'configuration', label: 'Configuración' },
  { id: 'review', label: 'Revisión' },
];
const inputClass = 'mt-1 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500';
const authLabels: Record<AuthMode, string> = { hmac_sha256: 'HMAC-SHA256', bearer: 'Bearer token', none: 'Sin autenticación' };

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
  const stepTitleRef = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    if (!isOpen) return;
    setForm(initialChannelForm(destination));
    setCurrentStep(0);
    setError(null);
  }, [isOpen, destination]);

  useEffect(() => {
    if (isOpen) stepTitleRef.current?.focus();
  }, [currentStep, isOpen]);

  const update = (patch: Partial<OutputChannelForm>) => {
    setForm((previous) => ({ ...previous, ...patch }));
    setError(null);
  };
  const close = () => { if (!submittingRef.current) onClose(); };
  const moveBack = (step: number) => {
    if (submittingRef.current) return;
    setError(null);
    setCurrentStep(step);
  };

  const next = async () => {
    if (submittingRef.current) return;
    const identityError = validateChannelIdentity(form, destinations, destination);
    const configurationError = validateChannelConfiguration(form, destination);
    const validationError = currentStep === 0 ? identityError : identityError ?? configurationError;
    if (validationError) {
      if (currentStep === 2) setCurrentStep(identityError ? 0 : 1);
      setError(validationError);
      return;
    }
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

  return (
    <Modal isOpen={isOpen} onClose={close} title={destination ? 'Editar canal de salida' : 'Añadir canal de salida'} size="large">
      <div className="flex min-h-[420px] flex-col">
        <StepperHeader steps={steps} currentStep={currentStep} onStepClick={moveBack} />
        <form className="flex flex-1 flex-col" onSubmit={(event) => { event.preventDefault(); void next(); }}>
          <fieldset disabled={submitting} className="min-w-0 flex-1 space-y-5 px-2 py-3">
            <h4 ref={stepTitleRef} tabIndex={-1} className="text-lg font-medium text-gray-900 outline-none">{steps[currentStep].label}</h4>
            {currentStep === 0 && <>
              <p className="text-sm text-gray-600">Elige el tipo de canal y un nombre para identificarlo en las tareas programadas.</p>
              <div role="group" aria-label="Tipo de canal" className="grid gap-3 sm:grid-cols-2">
                {([
                  { key: 'teams_workflow', label: 'Teams Workflow', description: 'Envía notificaciones a un canal de Teams.', icon: MessageSquare },
                  { key: 'webhook', label: 'Webhook HTTP', description: 'Envía resultados a un endpoint HTTPS.', icon: Webhook },
                ] as const).map(({ key, label, description, icon: Icon }) => <button
                  key={key} type="button" aria-pressed={form.provider === key} disabled={Boolean(destination)}
                  onClick={() => { if (form.provider !== key) update({ provider: key as ProviderKey, url: '', credential: '' }); }}
                  className={`rounded-lg border-2 p-4 text-left transition-colors disabled:cursor-default ${form.provider === key ? 'border-blue-600 bg-blue-50' : 'border-gray-200 hover:border-blue-300'}`}
                >
                  <Icon className="mb-2 h-6 w-6 text-blue-600" /><span className="block text-sm font-medium text-gray-900">{label}</span>
                  <span className="mt-1 block text-xs text-gray-600">{description}</span>
                </button>)}
              </div>
              {destination && <p className="text-xs text-gray-500">El tipo de canal se conserva. Para usar otro tipo, crea un nuevo canal.</p>}
              <label className="block text-sm font-medium text-gray-700"><span>Nombre del canal</span>
                <input value={form.name} onChange={(event) => update({ name: event.target.value })} maxLength={255} className={inputClass} placeholder="Por ejemplo: Alertas" autoComplete="off" />
              </label>
            </>}
            {currentStep === 1 && <>
              {(!destination || form.provider === 'teams_workflow') ? <label className="block text-sm font-medium text-gray-700">
                {form.provider === 'webhook' ? 'URL HTTPS del endpoint' : destination ? 'Nueva URL secreta del Workflow (opcional)' : 'URL del trigger de Teams'}
                <input type="url" value={form.url} onChange={(event) => update({ url: event.target.value })} className={inputClass} autoComplete="off" placeholder={destination ? 'Déjala vacía para conservar la URL guardada' : 'https://…'} />
                <span className="mt-2 block text-xs font-normal text-gray-500">{form.provider === 'teams_workflow'
                  ? destination ? 'Permite renovar la URL secreta del mismo Workflow. Para cambiar de Workflow o canal, crea un nuevo canal.' : 'La URL se guarda como credencial y no vuelve a mostrarse. Usa un trigger que acepte llamadas mediante URL.'
                  : 'El endpoint debe usar HTTPS y resolver únicamente a direcciones IP públicas.'}</span>
              </label> : <div className="rounded-lg border border-gray-200 bg-gray-50 p-3 text-sm text-gray-600">URL del endpoint guardada. Para cambiar el endpoint, crea un nuevo canal.</div>}
              <label className="block text-sm font-medium text-gray-700"><span>Contenido de la notificación</span>
                <select value={form.contentMode} onChange={(event) => update({ contentMode: event.target.value as OutputContentMode })} className={inputClass}>
                  {Object.entries(contentModeLabels(form.provider)).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                </select>
                <span className="mt-2 block text-xs font-normal text-gray-500">Se aplica a todas las tareas vinculadas a este canal.</span>
              </label>
              {form.provider === 'webhook' && <>
                <label className="block text-sm font-medium text-gray-700"><span>Autenticación</span>
                  <select value={form.authMode} onChange={(event) => update({ authMode: event.target.value as AuthMode, credential: '' })} className={inputClass}>
                    {Object.entries(authLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                  </select>
                </label>
                {form.authMode !== 'none' && <label className="block text-sm font-medium text-gray-700">
                  {form.authMode === 'hmac_sha256' ? 'Clave HMAC en Base64 (32 bytes)' : 'Bearer token'}
                  <input type="password" value={form.credential} onChange={(event) => update({ credential: event.target.value })} autoComplete="new-password" className={inputClass} />
                  {destination && destination.has_credentials && destination.public_config.auth_mode === form.authMode && <span className="mt-2 block text-xs font-normal text-gray-500">Deja este campo vacío para conservar la credencial guardada o introduce una nueva para renovarla.</span>}
                </label>}
                <div className="space-y-3 rounded-lg bg-gray-50 p-4">
                  <label className="flex items-start gap-2 text-sm text-gray-700"><input type="checkbox" checked={form.includeAttachments} onChange={(event) => update({ includeAttachments: event.target.checked })} className="mt-1" /><span>Enviar archivos adjuntos<span className="mt-1 block text-xs text-gray-500">Incluye los archivos en la llamada al webhook mediante multipart/form-data. Desactivado: envío JSON.</span></span></label>
                  <label className="flex items-start gap-2 text-sm text-gray-700"><input type="checkbox" checked={form.receiverDeduplicates} onChange={(event) => update({ receiverDeduplicates: event.target.checked })} className="mt-1" /><span>El receptor deduplica los eventos<span className="mt-1 block text-xs text-gray-500">Confirma que admite Idempotency-Key para permitir reintentos automáticos de resultado incierto.</span></span></label>
                </div>
              </>}
            </>}
            {currentStep === 2 && <>
              <p className="text-sm text-gray-600">Revisa la configuración antes de {destination ? 'guardar los cambios' : 'crear el canal'}.</p>
              <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-3 rounded-lg bg-gray-50 p-4 text-sm">
                <dt className="text-gray-500">Nombre</dt><dd className="break-words font-medium text-gray-900">{form.name.trim()}</dd>
                <dt className="text-gray-500">Tipo</dt><dd>{form.provider === 'webhook' ? 'Webhook HTTP' : 'Teams Workflow'}</dd>
                <dt className="text-gray-500">Contenido</dt><dd>{contentModeLabels(form.provider)[form.contentMode]}</dd>
                <dt className="text-gray-500">URL</dt><dd className="break-all">{form.url.trim() ? `${new URL(form.url.trim()).hostname} · ${destination ? 'Se renovará la URL secreta' : 'URL configurada'}` : 'Se conserva la URL guardada'}</dd>
                {form.provider === 'webhook' && <>
                  <dt className="text-gray-500">Autenticación</dt><dd>{authLabels[form.authMode]}</dd>
                  {form.authMode !== 'none' && <><dt className="text-gray-500">Credencial</dt><dd>{form.credential.trim() ? destination ? 'Se guardará una nueva credencial' : 'Configurada' : 'Se conserva la credencial guardada'}</dd></>}
                  <dt className="text-gray-500">Adjuntos</dt><dd>{form.includeAttachments ? 'Incluidos como archivos' : 'Desactivados'}</dd>
                  <dt className="text-gray-500">Deduplicación</dt><dd>{form.receiverDeduplicates ? 'Confirmada por el receptor' : 'Sin confirmar'}</dd>
                </>}
              </dl>
              <p className="text-xs text-gray-500">Tras guardar, podrás probar el destino desde el menú de acciones del listado.</p>
            </>}
          </fieldset>
          {error && <p role="alert" className="mt-3 px-2 text-sm text-red-600">{error}</p>}
          <StepperNavigation currentStep={currentStep} totalSteps={steps.length} onNext={() => { void next(); }} onBack={() => moveBack(currentStep - 1)} onCancel={close} backLabel="Atrás" cancelLabel="Cancelar" nextLabel={currentStep === 2 ? destination ? 'Guardar cambios' : 'Crear canal' : 'Siguiente'} isSubmitting={submitting} submittingLabel="Guardando…" />
        </form>
      </div>
    </Modal>
  );
}
