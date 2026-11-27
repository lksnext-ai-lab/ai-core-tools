import { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ArrowUpRight } from 'lucide-react';
import Modal from '../ui/Modal';
import { SidePanel } from '../ui/SidePanel';
import { useConfirm } from '../../contexts/ConfirmContext';
import { FormField, FormCheckbox } from '../ui/FormField';
import { FormActions } from '../ui/FormActions';
import Alert from '../ui/Alert';
import { ProviderBadge } from '../ui/Badge';
import { getProviderDescriptor } from './wizard/providers';
import ServiceWizard from './wizard/ServiceWizard';
import { dateInputValueFromIso, isoFromDateInput } from '../../utils/serviceLifecycle';
import ServiceLifecycleInputs from './ServiceLifecycleInputs';
import type {
  ExistingSandboxService,
  ExistingService,
  SandboxServiceFormData,
  ServiceFormData,
  ServiceKind,
  ServiceScope,
} from '../../types/services';

const MASKED_KEY_PREFIX = '****';

/** Provider-specific label for the secret field. */
const API_KEY_LABELS: Record<string, string> = {
  GoogleCloud: 'compactServiceEditor.apiKeyLabels.serviceAccountJson',
  Bedrock: 'compactServiceEditor.apiKeyLabels.awsSecretAccessKey',
};

interface CompactServiceEditorProps {
  readonly isOpen: boolean;
  readonly kind: ServiceKind;
  readonly scope: ServiceScope;
  readonly appId?: number;
  readonly service: ExistingService | ExistingSandboxService;
  readonly existingNames?: readonly string[];
  /**
   * `modal` (default) keeps the original centred dialog; `panel` renders the editor in a right
   * side panel (480 px) below the app header, with a fixed footer.
   */
  readonly variant?: 'modal' | 'panel';
  readonly onClose: () => void;
  /**
   * Method shorthand on purpose — see the identical note on
   * `ServiceWizardProps.onSave` for why this keeps bivariant parameter
   * checking so single-kind callers can keep a narrower handler type.
   */
  onSave(data: ServiceFormData | SandboxServiceFormData): Promise<void>;
}

function CompactServiceEditor({
  isOpen,
  kind,
  scope,
  appId,
  service,
  existingNames = [],
  variant = 'modal',
  onClose,
  onSave,
}: Readonly<CompactServiceEditorProps>) {
  const { t } = useTranslation('common');
  const confirm = useConfirm();
  const isPanel = variant === 'panel';
  const isSandbox = kind === 'sandbox';
  // Narrowed views of `service` — the two shapes only overlap on
  // name/provider/api_key/base_url/service_id. Field access for the
  // kind-specific extras goes through these instead of `service` directly.
  const aiService = !isSandbox ? (service as ExistingService) : null;
  const sandboxService = isSandbox ? (service as ExistingSandboxService) : null;

  const storedEndOfService = service.end_of_service_at;

  const descriptor = useMemo(
    () => getProviderDescriptor(service.provider),
    [service.provider],
  );
  const [name, setName] = useState(service.name);
  const [apiKey, setApiKey] = useState(service.api_key || '');
  const [apiKeyChanged, setApiKeyChanged] = useState(false);
  const [baseUrl, setBaseUrl] = useState(service.base_url || '');
  const [apiVersion, setApiVersion] = useState(aiService?.api_version || '');
  const [awsAccessKeyId, setAwsAccessKeyId] = useState(aiService?.aws_access_key_id || '');
  const [awsRegion, setAwsRegion] = useState(aiService?.aws_region || '');
  const [supportsVideo, setSupportsVideo] = useState(!!aiService?.supports_video);
  const [image, setImage] = useState(sandboxService?.opensandbox_image || '');
  const [target, setTarget] = useState(sandboxService?.daytona_target || '');
  const [template, setTemplate] = useState(sandboxService?.e2b_template || '');
  const [endOfServiceDate, setEndOfServiceDate] = useState(
    dateInputValueFromIso(storedEndOfService),
  );
  const [deprecationNotice, setDeprecationNotice] = useState(service.deprecation_notice || '');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showWizard, setShowWizard] = useState(false);

  // Reset state when the service prop changes (different service opened).
  useEffect(() => {
    setName(service.name);
    setApiKey(service.api_key || '');
    setApiKeyChanged(false);
    setBaseUrl(service.base_url || '');
    setApiVersion(aiService?.api_version || '');
    setAwsAccessKeyId(aiService?.aws_access_key_id || '');
    setAwsRegion(aiService?.aws_region || '');
    setSupportsVideo(!!aiService?.supports_video);
    setImage(sandboxService?.opensandbox_image || '');
    setTarget(sandboxService?.daytona_target || '');
    setTemplate(sandboxService?.e2b_template || '');
    setEndOfServiceDate(dateInputValueFromIso(storedEndOfService));
    setDeprecationNotice(service.deprecation_notice || '');
    setError(null);
  }, [service.service_id]);

  // ---- Unsaved changes: current editable values vs. the ones the service was opened with ----
  const currentSnapshot = JSON.stringify([
    name, apiKey, baseUrl, apiVersion, awsAccessKeyId, awsRegion, supportsVideo,
    image, target, template, endOfServiceDate, deprecationNotice,
  ]);
  const initialSnapshot = useMemo(
    () => JSON.stringify([
      service.name,
      service.api_key || '',
      service.base_url || '',
      aiService?.api_version || '',
      aiService?.aws_access_key_id || '',
      aiService?.aws_region || '',
      !!aiService?.supports_video,
      sandboxService?.opensandbox_image || '',
      sandboxService?.daytona_target || '',
      sandboxService?.e2b_template || '',
      dateInputValueFromIso(storedEndOfService),
      service.deprecation_notice || '',
    ]),
    // Same trigger as the reset effect above: a different service was opened.
    [service.service_id],
  );
  const isDirty = currentSnapshot !== initialSnapshot;
  const isConfirmingCloseRef = useRef(false);

  /**
   * Every way out (Cancel, X, Esc, backdrop) goes through here: with unsaved changes it asks
   * before discarding them. While the "change model" wizard is open on top, Esc belongs to it.
   */
  const requestClose = async () => {
    if (showWizard || isConfirmingCloseRef.current) return;
    if (!isDirty) {
      onClose();
      return;
    }
    isConfirmingCloseRef.current = true;
    const discard = await confirm({
      title: t('compactServiceEditor.discardTitle'),
      message: t('compactServiceEditor.discardMessage', { name: service.name }),
      confirmLabel: t('compactServiceEditor.discardConfirm'),
      cancelLabel: t('compactServiceEditor.keepEditing'),
      variant: 'danger',
    });
    // Released on the next tick so the same Esc keypress can't reopen the question.
    setTimeout(() => { isConfirmingCloseRef.current = false; }, 0);
    if (discard) onClose();
  };

  const showSupportsVideo =
    kind === 'ai' && (service.provider === 'Google' || service.provider === 'GoogleCloud');
  const showApiVersion = !!descriptor?.manualFields?.includes('api_version');
  const showAwsFields = !!descriptor?.manualFields?.includes('aws_access_key_id');
  const showImage = !!descriptor?.manualFields?.includes('image');
  const showTarget = !!descriptor?.manualFields?.includes('target');
  const showTemplate = !!descriptor?.manualFields?.includes('template');
  let baseUrlLabel = t('compactServiceEditor.baseUrl');
  if (service.provider === 'GoogleCloud') baseUrlLabel = t('compactServiceEditor.gcpProjectId');
  else if (service.provider === 'opensandbox') baseUrlLabel = t('compactServiceEditor.openSandboxDomain');
  else if (service.provider === 'daytona') baseUrlLabel = t('compactServiceEditor.daytonaApiUrl');
  const apiKeyLabel = t(API_KEY_LABELS[service.provider] ?? 'compactServiceEditor.apiKey');

  const handleApiKeyFocus = () => {
    if (!apiKeyChanged && apiKey.startsWith(MASKED_KEY_PREFIX)) {
      setApiKey('');
      setApiKeyChanged(true);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) {
      setError(t('compactServiceEditor.nameRequired'));
      return;
    }
    setError(null);
    setSubmitting(true);
    // If the user did not touch the field, send back the masked value so
    // the backend keeps the existing key untouched.
    const resolvedApiKey =
      apiKeyChanged || !apiKey.startsWith(MASKED_KEY_PREFIX) ? apiKey : service.api_key;

    // Always sent: an omitted field keeps its value, an explicit null clears it.
    // Keep a stored non-midnight timestamp untouched unless the day was changed.
    const resolvedEndOfService =
      storedEndOfService && dateInputValueFromIso(storedEndOfService) === endOfServiceDate
        ? storedEndOfService
        : isoFromDateInput(endOfServiceDate);
    const resolvedNotice = deprecationNotice.trim() || null;

    const payload: ServiceFormData | SandboxServiceFormData = isSandbox
      ? {
          name: name.trim(),
          provider: service.provider,
          api_key: resolvedApiKey,
          base_url: baseUrl,
          opensandbox_image: showImage ? image.trim() || undefined : undefined,
          daytona_target: showTarget ? target.trim() || undefined : undefined,
          e2b_template: showTemplate ? template.trim() || undefined : undefined,
          end_of_service_at: resolvedEndOfService,
          deprecation_notice: resolvedNotice,
        }
      : {
          name: name.trim(),
          provider: service.provider,
          model_name: aiService?.model_name || '',
          api_key: resolvedApiKey,
          base_url: baseUrl,
          api_version: apiVersion || undefined,
          supports_video: supportsVideo,
          aws_access_key_id: showAwsFields ? awsAccessKeyId.trim() || undefined : undefined,
          aws_region: showAwsFields ? awsRegion.trim() || undefined : undefined,
          end_of_service_at: resolvedEndOfService,
          deprecation_notice: resolvedNotice,
        };
    try {
      await onSave(payload);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('compactServiceEditor.saveFailed'));
    } finally {
      setSubmitting(false);
    }
  };

  const handleWizardSave = async (data: ServiceFormData | SandboxServiceFormData) => {
    // The wizard owns the full edit-model flow, so once it saves we're done.
    await onSave(data);
    setShowWizard(false);
  };

  const form = (
        <form onSubmit={handleSubmit} className={isPanel ? 'space-y-4 px-4 pt-3' : 'space-y-4'}>
          {isPanel && (
            <h2 className="font-display text-[21px] font-normal tracking-[-0.02em] text-fg dark:text-fg-dark">
              {t('compactServiceEditor.title')}
            </h2>
          )}
          {error && <Alert type="error" message={error} />}

          <div className="rounded-md border border-line-strong dark:border-line-strong-dark bg-canvas-alt dark:bg-canvas-alt-dark p-3 space-y-3">
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-[11px] uppercase font-semibold text-bronze dark:text-bronze-dark tracking-wide">
                  {t('compactServiceEditor.provider')}
                </p>
                <ProviderBadge
                  provider={service.provider}
                  label={descriptor?.label || service.provider}
                  className="mt-1"
                />
              </div>
              {!isSandbox && (
                <div className="text-right">
                  <p className="text-[11px] uppercase font-semibold text-bronze dark:text-bronze-dark tracking-wide">
                    {t('compactServiceEditor.model')}
                  </p>
                  <p className="text-sm font-mono text-fg dark:text-fg-dark mt-1">
                    {aiService?.model_name}
                  </p>
                </div>
              )}
              <button
                type="button"
                onClick={() => setShowWizard(true)}
                className="text-sm font-medium text-bronze  dark:text-bronze-dark inline-block items-center gap-1"
              >
                 {isSandbox ? t('compactServiceEditor.editConfiguration') : t('compactServiceEditor.changeModel')}
                 <ArrowUpRight className="w-4 h-4 inline-block ml-1" aria-hidden="true" />

              </button>
            </div>
          </div>

          <FormField
            id="name"
            label={t('compactServiceEditor.name')}
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            helpText={t('compactServiceEditor.nameHelp')}
          />

          {descriptor?.apiKey !== 'none' && (
            <FormField
              id="api_key"
              type="password"
              label={<>
                {apiKeyLabel}
                {descriptor?.apiKey === 'optional' && (
                  <span className="text-fg-tertiary dark:text-fg-tertiary-dark font-normal"> ({t('compactServiceEditor.optional')})</span>
                )}
              </>}
              autoComplete="off"
              data-lpignore="true"
              value={apiKey}
              onChange={(e) => {
                setApiKey(e.target.value);
                setApiKeyChanged(true);
              }}
              onFocus={handleApiKeyFocus}
              placeholder={descriptor?.apiKeyPlaceholder}
              helpText={t('compactServiceEditor.keepMaskedApiKey')}
            />
          )}

          {descriptor?.needsBaseUrl && (
            <FormField
              id="base_url"
              label={baseUrlLabel}
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              placeholder={descriptor.baseUrlPlaceholder}
            />
          )}

          {showApiVersion && (
            <FormField
              id="api_version"
              label={service.provider === 'GoogleCloud' ? t('compactServiceEditor.region') : t('compactServiceEditor.apiVersion')}
              value={apiVersion}
              onChange={(e) => setApiVersion(e.target.value)}
            />
          )}

          {showAwsFields && (
            <>
              <FormField
                id="aws_access_key_id"
                label={t('compactServiceEditor.awsAccessKeyId')}
                value={awsAccessKeyId}
                onChange={(e) => setAwsAccessKeyId(e.target.value)}
                placeholder="AKIA..."
                required
              />
              <FormField
                id="aws_region"
                label={t('compactServiceEditor.awsRegion')}
                value={awsRegion}
                onChange={(e) => setAwsRegion(e.target.value)}
                placeholder="us-east-1"
                required
              />
            </>
          )}

          {showImage && (
            <FormField
              id="image"
              label={t('compactServiceEditor.containerImage')}
              value={image}
              onChange={(e) => setImage(e.target.value)}
              placeholder="python:3.11-slim"
              helpText={t('compactServiceEditor.containerImageHelp')}
            />
          )}

          {showTarget && (
            <FormField
              id="target"
              label={t('compactServiceEditor.target')}
              value={target}
              onChange={(e) => setTarget(e.target.value)}
              placeholder="us"
              helpText={t('compactServiceEditor.targetHelp')}
            />
          )}

          {showTemplate && (
            <FormField
              id="template"
              label={t('compactServiceEditor.template')}
              value={template}
              onChange={(e) => setTemplate(e.target.value)}
              placeholder="base"
              helpText={t('compactServiceEditor.templateHelp')}
            />
          )}

          <ServiceLifecycleInputs
            date={endOfServiceDate}
            notice={deprecationNotice}
            onDateChange={setEndOfServiceDate}
            onNoticeChange={setDeprecationNotice}
          />

          {showSupportsVideo && (
            <FormCheckbox
              id="supports_video"
              label={t('compactServiceEditor.videoAnalysisCapable')}
              checked={supportsVideo}
              onChange={(e) => setSupportsVideo(e.target.checked)}
            />
          )}

          <div
            className={isPanel
              // Fixed footer: sticks to the bottom of the side panel's scroll area.
              ? 'sticky -bottom-4 z-10 -mx-[1.625rem] -mb-4 border-t border-line bg-surface px-[1.625rem] py-4 dark:border-line-dark dark:bg-surface-dark'
              : 'pt-2'}
          >
            <FormActions
              onCancel={() => { void requestClose(); }}
              isSubmitting={submitting}
              isEditing
              submitDisabled={!name.trim() || !isDirty}
              containerClassName={isPanel ? '!border-t-0 !pt-0' : ''}
            />
          </div>
        </form>
  );

  return (
    <>
      {isPanel ? (
        isOpen && (
          // Fixed wrapper starting below the 56px (h-14) app header, like the "Used by" panel.
          <div className="fixed inset-x-0 bottom-0 top-14 z-30 !mt-0">
            <SidePanel
              open
              side="right"
              onClose={() => { void requestClose(); }}
              title={t('compactServiceEditor.panelLabel')}
              closeLabel={t('compactServiceEditor.closePanel')}
              widthClassName="w-[480px] max-w-full"
            >
              {form}
            </SidePanel>
          </div>
        )
      ) : (
        <Modal
          isOpen={isOpen && !showWizard}
          onClose={() => { void requestClose(); }}
          title={t('compactServiceEditor.title')}
        >
          {form}
        </Modal>
      )}

      {showWizard && (
        <ServiceWizard
          isOpen={showWizard}
          kind={kind}
          scope={scope}
          appId={appId}
          mode="edit-model"
          initialService={service}
          existingNames={existingNames.filter((n) => n !== service.name)}
          onClose={() => setShowWizard(false)}
          onSave={handleWizardSave}
        />
      )}
    </>
  );
}

export default CompactServiceEditor;
