import { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Check, CheckCircle2, XCircle, WifiOff, HelpCircle, Plug } from 'lucide-react';
import { apiService } from '../../services/api';
import Alert from '../../components/ui/Alert';
import { useAppRole } from '../../hooks/useAppRole';
import { AppRole } from '../../types/roles';
import ReadOnlyBanner from '../../components/ui/ReadOnlyBanner';
import { LoadingState } from '../../components/ui/LoadingState';
import { ButtonApp } from '../../components/ui/ButtonApp';
import { Spinner } from '../../components/ui/Spinner';
import { FormCheckbox, FormField, FormSelect } from '../../components/ui/FormField';
import Title from '../../components/ui/Title';
import AppAvatar from '../../components/ui/AppAvatar';
import ImageUploadControl from '../../components/ui/ImageUploadControl';
import { useAuthenticatedImage } from '../../hooks/useAuthenticatedImage';
import { ServiceOptionStatus, serviceStatusId } from '../../components/ui/ServiceOptionStatus';
import { selectableServiceOptions, serviceOptionLabel, type ServiceOptionLike } from '../../utils/serviceLifecycle';

type LangsmithTestStatus = 'ok' | 'unauthorized' | 'network' | 'unknown';

interface LangsmithTestResult {
  readonly status: LangsmithTestStatus;
  readonly message: string;
  readonly projectName?: string | null;
}

interface EmbeddingServiceOption extends ServiceOptionLike {
  readonly provider: string;
  readonly model_name?: string;
  readonly is_system?: boolean;
}

interface SandboxServiceOption extends ServiceOptionLike {
  readonly provider: string;
  readonly is_system?: boolean;
}

function AppSettingsPage() {
  const { t } = useTranslation('common');
  const { appId } = useParams();
  const { hasMinRole, userRole } = useAppRole(appId);
  const canEdit = hasMinRole(AppRole.ADMINISTRATOR);
  // The LangSmith API key stays owner-only: administrators edit the rest of the settings but never this key.
  const canEditLangsmith = hasMinRole(AppRole.OWNER);

  const [formData, setFormData] = useState({
    name: '',
    langsmith_api_key: '',
    agent_rate_limit: 0,
    max_file_size_mb: 0,
    agent_cors_origins: '',
    enable_openai_api: false,
    default_sandbox_service_id: null as number | null,  // null = inherit system default
    chat_code_interpreter_enabled: false,
    default_embedding_service_id: null as number | null,  // null = none (Chat attachments are not indexed)
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [langsmithKeyChanged, setLangsmithKeyChanged] = useState(false);
  const [originalLangsmithKey, setOriginalLangsmithKey] = useState('');
  const [testingLangsmith, setTestingLangsmith] = useState(false);
  const [langsmithTestResult, setLangsmithTestResult] = useState<LangsmithTestResult | null>(null);

  const [slugInput, setSlugInput] = useState('');
  const [savingSlug, setSavingSlug] = useState(false);
  const [slugSaved, setSlugSaved] = useState(false);
  const [slugError, setSlugError] = useState<string | null>(null);
  // Saved (loaded) default sandbox: a retired service stays selectable only if it is this one (D-4).
  const [imageVersion, setImageVersion] = useState<string | null>(null);
  const [imageMessage, setImageMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const imageUrl = useAuthenticatedImage(appId ?? null, imageVersion, (version) =>
    apiService.getAppImage(Number.parseInt(appId ?? ''), version));
  const [savedSandboxServiceId, setSavedSandboxServiceId] = useState<number | null>(null);
  const [sandboxServices, setSandboxServices] = useState<SandboxServiceOption[]>([]);
  const [savedEmbeddingServiceId, setSavedEmbeddingServiceId] = useState<number | null>(null);
  const [embeddingServices, setEmbeddingServices] = useState<EmbeddingServiceOption[]>([]);
  const [embeddingServicesFailed, setEmbeddingServicesFailed] = useState(false);

  // Load app data on mount
  useEffect(() => {
    if (appId) {
      void loadAppData();
      void loadSlugData();
      void loadSandboxServices();
      void loadEmbeddingServices();
    }
  }, [appId]);

  async function loadSandboxServices() {
    if (!appId) return;
    try {
      const services = await apiService.getSandboxServices(Number.parseInt(appId)) as SandboxServiceOption[];
      setSandboxServices(services ?? []);
    } catch (err) {
      console.error('Error loading sandbox services:', err);
    }
  }

  async function loadEmbeddingServices() {
    if (!appId) return;
    try {
      const services = await apiService.getEmbeddingServices(Number.parseInt(appId)) as EmbeddingServiceOption[];
      setEmbeddingServices(services ?? []);
      setEmbeddingServicesFailed(false);
    } catch (err) {
      setEmbeddingServicesFailed(true);
      console.error('Error loading embedding services:', err);
    }
  }

  async function loadAppData() {
    if (!appId) return;

    try {
      setLoading(true);
      setError(null);
      const app = await apiService.getApp(Number.parseInt(appId));
      const langsmithKey = app.langsmith_api_key || '';
      setFormData({
        name: app.name || '',
        langsmith_api_key: langsmithKey,
        agent_rate_limit: app.agent_rate_limit || 0,
        max_file_size_mb: app.max_file_size_mb || 0,
        agent_cors_origins: app.agent_cors_origins || '',
        enable_openai_api: app.enable_openai_api || false,
        default_sandbox_service_id: app.default_sandbox_service_id ?? null,
        chat_code_interpreter_enabled: app.chat_code_interpreter_enabled ?? false,
        default_embedding_service_id: app.default_embedding_service_id ?? null,
      });
      setImageVersion(app.image_updated_at ?? null);
      setSavedSandboxServiceId(app.default_sandbox_service_id ?? null);
      setSavedEmbeddingServiceId(app.default_embedding_service_id ?? null);
      setOriginalLangsmithKey(langsmithKey);
      setLangsmithKeyChanged(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('appSettingsPage.loadFailed'));
      console.error('Error loading app data:', err);
    } finally {
      setLoading(false);
    }
  }

  async function uploadImage(file: File) {
    const { image_updated_at } = await apiService.uploadAppImage(Number.parseInt(appId ?? ''), file);
    setImageVersion(image_updated_at);
  }

  async function removeImage() {
    await apiService.deleteAppImage(Number.parseInt(appId ?? ''));
    setImageVersion(null);
  }

  async function loadSlugData() {
    if (!appId) return;

    try {
      const data = await apiService.getAppSlugInfo(Number.parseInt(appId));
      setSlugInput(data.slug || '');
    } catch (err) {
      console.error('Error loading slug data:', err);
    }
  }

  async function handleSlugSubmit(e?: React.FormEvent | React.MouseEvent) {
    e?.preventDefault();
    if (!appId || !slugInput.trim()) return;

    setSavingSlug(true);
    setSlugError(null);

    try {
      const data = await apiService.updateAppSlug(Number.parseInt(appId), slugInput.trim());
      setSlugInput(data.slug || '');
      setSlugSaved(true);
      setTimeout(() => setSlugSaved(false), 3000);
    } catch (err) {
      setSlugError(err instanceof Error ? err.message : t('appSettingsPage.slugUpdateFailed'));
      console.error('Error updating slug:', err);
    } finally {
      setSavingSlug(false);
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!appId) return;
    
    setSaving(true);
    setError(null);

    try {
      await apiService.updateApp(Number.parseInt(appId), {
        name: formData.name,
        // Non-owners never send the key (the backend refuses a change and keeps the stored one when it is omitted).
        ...(canEditLangsmith
          ? { langsmith_api_key: langsmithKeyChanged ? formData.langsmith_api_key : originalLangsmithKey }
          : {}),
        agent_rate_limit: formData.agent_rate_limit,
        max_file_size_mb: formData.max_file_size_mb,
        agent_cors_origins: formData.agent_cors_origins,
        enable_openai_api: formData.enable_openai_api,
        default_sandbox_service_id: formData.default_sandbox_service_id,
        chat_code_interpreter_enabled: formData.chat_code_interpreter_enabled,
        default_embedding_service_id: formData.default_embedding_service_id,
      });
      setSavedSandboxServiceId(formData.default_sandbox_service_id);
      setSavedEmbeddingServiceId(formData.default_embedding_service_id);
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('appSettingsPage.saveFailed'));
      console.error('Error saving app settings:', err);
    } finally {
      setSaving(false);
    }
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newValue = (e.target.name === 'agent_rate_limit' || e.target.name === 'max_file_size_mb')
      ? Number.parseInt(e.target.value) || 0
      : e.target.type === 'checkbox'
      ? e.target.checked
      : e.target.value;

    if (e.target.name === 'langsmith_api_key') {
      setLangsmithKeyChanged(true);
      setLangsmithTestResult(null);
    }

    setFormData(prev => ({
      ...prev,
      [e.target.name]: newValue
    }));
  };

  async function handleTestLangsmith() {
    if (!appId) return;

    setTestingLangsmith(true);
    setLangsmithTestResult(null);

    try {
      const keyToTest = langsmithKeyChanged ? formData.langsmith_api_key : undefined;
      const result = await apiService.testAppLangsmith(Number.parseInt(appId), keyToTest);
      setLangsmithTestResult({
        status: result.status,
        message: result.message,
        projectName: result.project_name ?? null,
      });
    } catch (err) {
      setLangsmithTestResult({
        status: 'unknown',
        message: err instanceof Error ? err.message : t('appSettingsPage.langsmithTestFailed'),
      });
    } finally {
      setTestingLangsmith(false);
    }
  }

  const canTestLangsmith = (langsmithKeyChanged
    ? Boolean(formData.langsmith_api_key.trim())
    : Boolean(originalLangsmithKey));

  if (loading) {
    return (
      
        <LoadingState variant="page" message={t('appSettingsPage.loading')} />
      
    );
  }

  if (error) {
    return (
      <div className="p-6">
        <Alert 
          type="error" 
          title={t('appSettingsPage.loadErrorTitle')}
          message={error}
          onDismiss={loadAppData}
        />
      </div>
    );
  }

  return (
    
      <div className="p-6">
        <div className="max-w-2xl">
          <Title
            variant="titSecundario"
            titulo={t('appSettingsPage.generalSettings')}
            subtitulo={t('appSettingsPage.subtitle')}
          />
          {!canEdit && <ReadOnlyBanner userRole={userRole} minRole={AppRole.ADMINISTRATOR} />}
          {/* Settings Form */}
          <form onSubmit={handleSubmit} className="space-y-6">
            <div >
              <div className="grid grid-cols-1 gap-6">
                {/* App Image */}
                <div>
                  <span className="block text-sm font-medium text-fg dark:text-fg-dark mb-1">{t('appSettingsPage.image.label')}</span>
                  <div className="flex flex-wrap items-center gap-4">
                    <AppAvatar name={formData.name} src={imageUrl} size={64} />
                    {canEdit && (
                      <ImageUploadControl
                        hasImage={Boolean(imageVersion)}
                        inputLabel={t('appSettingsPage.image.inputLabel')}
                        onUpload={uploadImage}
                        onRemove={removeImage}
                        onSuccess={(text) => setImageMessage({ type: 'success', text })}
                        onError={(text) => setImageMessage({ type: 'error', text })}
                      />
                    )}
                  </div>
                  <p className="mt-1 text-xs text-fg-tertiary dark:text-fg-tertiary-dark">{t('appSettingsPage.image.help')}</p>
                  {imageMessage && (
                    <Alert
                      type={imageMessage.type}
                      message={imageMessage.text}
                      onDismiss={() => setImageMessage(null)}
                      className="mt-2"
                    />
                  )}
                </div>

                {/* App Name */}
                <FormField
                  label={t('appSettingsPage.appName')}
                  id="name"
                  name="name"
                  value={formData.name}
                  onChange={handleChange}
                  required
                  disabled={!canEdit}
                  placeholder={t('appSettingsPage.appNamePlaceholder')}
                />

                {/* App Slug */}
                <div className="flex items-start gap-2">
                  <FormField
                    className="flex-1"
                    label={t('appSettingsPage.appSlug')}
                    id="slug"
                    value={slugInput}
                    onChange={(e) => setSlugInput(e.target.value.toLowerCase().replaceAll(/[^a-z0-9-]/g, ''))}
                    disabled={!canEdit}
                    placeholder={t('appSettingsPage.appSlugPlaceholder')}
                    pattern="[a-z0-9-]+"
                    helpText={t('appSettingsPage.appSlugHelp')}
                  />
                  {canEdit && (
                    <ButtonApp
                      label={savingSlug ? t('appSettingsPage.saving') : t('appSettingsPage.updateSlug')}
                      onClick={handleSlugSubmit}
                      disabled={!slugInput.trim()}
                      loading={savingSlug}
                      variant="secondary"
                      className="mt-6 whitespace-nowrap"
                    />
                  )}
                  {slugSaved && (
                    <p className="mt-1 text-sm text-green-600 flex items-center">
                      <Check className="w-4 h-4 mr-1" /> {t('appSettingsPage.slugSaved')}
                    </p>
                  )}
                  {slugError && (
                    <p className="mt-1 text-sm text-error dark:text-error-dark">{slugError}</p>
                  )}
                </div>

                {/* Langsmith API Key */}
                <div>
                  <div className="flex items-start gap-2">
                    <FormField
                      className="flex-1"
                      label={t('appSettingsPage.langsmithApiKey')}
                      id="langsmith_api_key"
                      name="langsmith_api_key"
                      type="password"
                      value={formData.langsmith_api_key}
                      onChange={handleChange}
                      onKeyDown={(e) => {
                        if (!langsmithKeyChanged && formData.langsmith_api_key.startsWith('****') && e.key.length === 1) {
                          setFormData(prev => ({ ...prev, langsmith_api_key: '' }));
                          setLangsmithKeyChanged(true);
                          setLangsmithTestResult(null);
                        }
                      }}
                      autoComplete="off"
                      data-lpignore="true"
                      data-form-type="other"
                      disabled={!canEditLangsmith}
                      placeholder={!langsmithKeyChanged && originalLangsmithKey
                        ? t('appSettingsPage.keepCurrentKeyPlaceholder')
                        : t('appSettingsPage.enterLangsmithKeyPlaceholder')}
                      helpText={(
                        <>
                          {t('appSettingsPage.langsmithHelpBeforeKey')}{' '}
                          <code className="mx-1 bg-gray-100 px-1 rounded text-xs">LANGSMITH_API_KEY</code>
                          {t('appSettingsPage.langsmithHelpBetweenKeys')}{' '}
                          <code className="mx-1 bg-gray-100 px-1 rounded text-xs">LANGSMITH_TRACING=true</code>).
                          {!canEditLangsmith && (
                            <span className="mt-1 block font-medium">{t('appSettingsPage.langsmithOwnerOnly')}</span>
                          )}
                        </>
                      )}
                    />
                    {canEditLangsmith && (
                      <button
                        type="button"
                        onClick={handleTestLangsmith}
                        disabled={testingLangsmith || !canTestLangsmith}
                        className="mt-6 inline-flex cursor-pointer items-center justify-center gap-2 whitespace-nowrap rounded-md border border-ink bg-surface px-[15px] py-[9px] font-display text-sm font-normal tracking-[-0.02em] text-fg transition-colors hover:bg-surface-hover disabled:cursor-not-allowed disabled:opacity-50 dark:border-ink-dark dark:bg-surface-dark dark:text-fg-dark dark:hover:bg-surface-hover-dark"
                        title={t('appSettingsPage.testLangsmithTitle')}
                      >
                        {testingLangsmith ? (
                          <Spinner size="sm" tone="current" />
                        ) : (
                          <Plug className="w-4 h-4" />
                        )}
                        {testingLangsmith ? t('appSettingsPage.testing') : t('appSettingsPage.testConnection')}
                      </button>
                    )}
                  </div>
                  {langsmithTestResult && (
                    <div
                      role="status"
                      className={`mt-2 inline-flex items-center text-sm rounded-md px-3 py-1.5 border ${
                        langsmithTestResult.status === 'ok'
                          ? 'bg-green-50 text-green-700 border-green-200'
                          : langsmithTestResult.status === 'unauthorized'
                          ? 'bg-red-50 text-red-700 border-red-200'
                          : langsmithTestResult.status === 'network'
                          ? 'bg-amber-50 text-amber-700 border-amber-200'
                          : 'bg-gray-50 text-gray-700 border-gray-200'
                      }`}
                    >
                      {langsmithTestResult.status === 'ok' && <CheckCircle2 className="w-4 h-4 mr-2" />}
                      {langsmithTestResult.status === 'unauthorized' && <XCircle className="w-4 h-4 mr-2" />}
                      {langsmithTestResult.status === 'network' && <WifiOff className="w-4 h-4 mr-2" />}
                      {langsmithTestResult.status === 'unknown' && <HelpCircle className="w-4 h-4 mr-2" />}
                      <span>
                        {langsmithTestResult.status === 'ok' && langsmithTestResult.projectName
                          ? t('appSettingsPage.connectedToProject', { projectName: langsmithTestResult.projectName })
                          : langsmithTestResult.message}
                      </span>
                    </div>
                  )}
                </div>

                {/* Agent rate limit */}
                <FormField
                  label={t('appSettingsPage.agentRateLimit')}
                  id="agent_rate_limit"
                  name="agent_rate_limit"
                  type="number"
                  value={formData.agent_rate_limit}
                  onChange={handleChange}
                  min={0}
                  disabled={!canEdit}
                  placeholder={t('appSettingsPage.agentRateLimitPlaceholder')}
                  helpText={t('appSettingsPage.agentRateLimitHelp')}
                />

                {/* Maximum File Size */}
                <FormField
                  label={t('appSettingsPage.maxFileSize')}
                  id="max_file_size_mb"
                  name="max_file_size_mb"
                  type="number"
                  value={formData.max_file_size_mb}
                  onChange={handleChange}
                  min={0}
                  disabled={!canEdit}
                  placeholder={t('appSettingsPage.maxFileSizePlaceholder')}
                  helpText={t('appSettingsPage.maxFileSizeHelp')}
                />

                {/* Agent CORS Origins */}
                <FormField
                  label={t('appSettingsPage.agentCorsOrigins')}
                  id="agent_cors_origins"
                  name="agent_cors_origins"
                  value={formData.agent_cors_origins}
                  onChange={handleChange}
                  disabled={!canEdit}
                  placeholder={t('appSettingsPage.agentCorsOriginsPlaceholder')}
                  helpText={t('appSettingsPage.agentCorsOriginsHelp')}
                />

                {/* Enable OpenAI-compatible API */}
                <FormCheckbox
                  label={t('appSettingsPage.enableOpenAiApi')}
                  id="enable_openai_api"
                  checked={formData.enable_openai_api}
                  onChange={handleChange}
                  disabled={!canEdit}
                  helpText={t('appSettingsPage.enableOpenAiApiHelp')}
                />

                {/* Sandbox Service */}
                <div>
                  <FormSelect
                    label={t('appSettingsPage.sandboxService')}
                    id="default_sandbox_service_id"
                    value={formData.default_sandbox_service_id ?? ''}
                    onChange={(e) => setFormData(prev => ({
                      ...prev,
                      default_sandbox_service_id: e.target.value ? Number.parseInt(e.target.value) : null,
                    }))}
                    disabled={!canEdit}
                    ariaDescribedBy={serviceStatusId(sandboxServices, formData.default_sandbox_service_id, 'default_sandbox_service_id')}
                    options={[
                      { value: '', label: t('appSettingsPage.inheritSystemDefault') },
                      ...selectableServiceOptions(sandboxServices, savedSandboxServiceId).map((service) => ({
                        value: service.service_id,
                        label: serviceOptionLabel(
                          service,
                          `${service.is_system ? t('appSettingsPage.systemServiceOption', { name: service.name }) : service.name} (${service.provider})`,
                        ),
                      })),
                    ]}
                    helpText={(
                      <>
                        {t('appSettingsPage.sandboxServiceHelpBeforeSettings')}{' '}
                        <span className="font-medium">{t('appSettingsPage.sandboxServicesSettings')}</span>.
                      </>
                    )}
                  />
                  <ServiceOptionStatus selectId="default_sandbox_service_id" options={sandboxServices} selectedId={formData.default_sandbox_service_id} />
                </div>

                {/* Code interpreter in the App Chat (uses the default sandbox service above) */}
                <div>
                  <FormCheckbox
                    label={t('appSettingsPage.chatCodeInterpreter')}
                    id="chat_code_interpreter_enabled"
                    checked={formData.chat_code_interpreter_enabled}
                    onChange={handleChange}
                    disabled={!canEdit}
                    helpText={t('appSettingsPage.chatCodeInterpreterHelp')}
                  />
                </div>

                {/* Default embedding service (indexes files attached in the App Chat) */}
                <div>
                  <FormSelect
                    label={t('appSettingsPage.embeddingService')}
                    id="default_embedding_service_id"
                    value={formData.default_embedding_service_id ?? ''}
                    onChange={(e) => setFormData(prev => ({
                      ...prev,
                      default_embedding_service_id: e.target.value ? Number.parseInt(e.target.value) : null,
                    }))}
                    disabled={!canEdit}
                    ariaDescribedBy={serviceStatusId(embeddingServices, formData.default_embedding_service_id, 'default_embedding_service_id')}
                    options={[
                      { value: '', label: t('appSettingsPage.noDefaultEmbeddingService') },
                      ...selectableServiceOptions(embeddingServices, savedEmbeddingServiceId).map((service) => ({
                        value: service.service_id,
                        label: serviceOptionLabel(
                          service,
                          `${service.is_system ? t('appSettingsPage.systemServiceOption', { name: service.name }) : service.name} (${service.provider})`,
                        ),
                      })),
                    ]}
                    helpText={(
                      <>
                        {t('appSettingsPage.embeddingServiceHelpBeforeSettings')}{' '}
                        <span className="font-medium">{t('appSettingsPage.embeddingServicesSettings')}</span>.
                      </>
                    )}
                  />
                  <ServiceOptionStatus selectId="default_embedding_service_id" options={embeddingServices} selectedId={formData.default_embedding_service_id} />
                  {embeddingServicesFailed && (
                    <Alert type="warning" message={t('appSettingsPage.embeddingServicesLoadFailed')} className="mt-2" />
                  )}
                </div>
              </div>

              {/* Error Display */}
              {error && <Alert type="error" title={t('appSettingsPage.saveErrorTitle')} message={error} className="mt-4" />}

              {/* Submit Button - Only show for admins */}
              {canEdit && (
                <div className="mt-6 flex items-center justify-between">
                  <div className="flex items-center">
                    {saved && (
                      <div className="flex items-center text-green-600">
                        <Check className="w-4 h-4 mr-1" /> {t('appSettingsPage.settingsSaved')}
                      </div>
                    )}
                  </div>
                  <ButtonApp
                    type="submit"
                    label={saving ? t('appSettingsPage.saving') : t('appSettingsPage.saveChanges')}
                    loading={saving}
                  />
                </div>
              )}
            </div>
          </form>

          {/* Info Sections */}
          <div className="mt-8 space-y-6">
            {/* App Slug Info */}
            <Alert
              type="info"
              title={t('appSettingsPage.aboutAppSlug')}
              message={(
                <p>
                  {t('appSettingsPage.aboutAppSlugDescription')}{' '}
                  <code className="bg-gray-200 px-1 rounded text-xs">/mcp/v1/my-app/my-server</code>{' '}
                  {t('appSettingsPage.aboutAppSlugSuffix')}
                </p>
              )}
            />

            {/* Langsmith Info */}
            <Alert
              type="info"
              title={t('appSettingsPage.aboutLangsmithTitle')}
              message={t('appSettingsPage.aboutLangsmithMessage')}
            />

            {/* OpenAI-compatible API Info */}
            <Alert
              type="info"
              title={t('appSettingsPage.aboutOpenAiApiTitle')}
              message={(
                <>
                  <p className="mb-2">{t('appSettingsPage.aboutOpenAiApiMessage')}</p>
                  <p className="mb-2">
                    <strong>{t('appSettingsPage.openAiApiImpact')}</strong>
                  </p>
                  <ul className="list-disc list-inside space-y-1">
                    <li>{t('appSettingsPage.openAiApiImpactCompatibility')}</li>
                    <li>{t('appSettingsPage.openAiApiImpactEndpoints')}</li>
                    <li>{t('appSettingsPage.openAiApiImpactIntegration')}</li>
                    <li>{t('appSettingsPage.openAiApiImpactExisting')}</li>
                  </ul>
                </>
              )}
            />

            {/* App Settings Info */}
            <Alert
              type="info"
              title={t('appSettingsPage.appConfigurationTitle')}
              message={t('appSettingsPage.appConfigurationMessage')}
            />

            {/* Sandbox Service Info */}
            <Alert
              type="info"
              title={t('appSettingsPage.aboutSandboxServicesTitle')}
              message={(
                <>
                  <p className="mb-2">
                    {t('appSettingsPage.aboutSandboxServicesMessageBeforeSettings')}{' '}
                    <strong>{t('appSettingsPage.sandboxServicesSettings')}</strong>.
                  </p>
                  <ul className="list-disc list-inside space-y-1">
                    <li><strong>{t('appSettingsPage.selectService')}</strong> — {t('appSettingsPage.selectServiceDescription')}</li>
                    <li><strong>{t('appSettingsPage.inherit')}</strong> — {t('appSettingsPage.inheritDescription')}</li>
                  </ul>
                </>
              )}
            />
          </div>
        </div>
      </div>
    
  );
}

export default AppSettingsPage; 
