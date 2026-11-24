import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { StepperContainer } from '../components/ui/Stepper';
import type { StepDefinition } from '../components/ui/Stepper';
import { TagInput } from '../components/ui/TagInput';
import Alert from '../components/ui/Alert';
import { sharepointApi } from '../services/sharepoint';
import { apiService } from '../services/api';
import type { MicrosoftDrive } from '../types/sharepoint';
import { ButtonApp } from '../components/ui/ButtonApp';
import { Spinner } from '../components/ui/Spinner';
import Title from '../components/ui/Title';
import { FormField, FormRadio, FormSelect, FormTextArea } from '../components/ui/FormField';
import { ServiceOptionStatus, serviceStatusId } from '../components/ui/ServiceOptionStatus';
import { selectableServiceOptions, serviceOptionLabel, type ServiceOptionLike } from '../utils/serviceLifecycle';

interface Credentials {
  tenant_id: string;
  client_id: string;
  client_secret: string;
}

interface SiteSelection {
  site_id: string;
  site_name: string;
  site_url: string;
}

interface DriveSelection {
  drive_id: string;
  drive_name: string;
}

type EmbeddingService = ServiceOptionLike;

function SharePointWizardPage() {
  const { appId } = useParams<{ appId: string }>();
  const navigate = useNavigate();
  const { t } = useTranslation('common');
  const wizardSteps: StepDefinition[] = [
    { id: 'connect', label: t('sharePointWizardPage.steps.connect') },
    { id: 'drive', label: t('sharePointWizardPage.steps.drive') },
    { id: 'indexing', label: t('sharePointWizardPage.steps.indexing') },
  ];
  const [step, setStep] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // Step 1 — credentials
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [creds, setCreds] = useState<Credentials>({
    tenant_id: '',
    client_id: '',
    client_secret: '',
  });
  const [testingConnection, setTestingConnection] = useState(false);

  // Step 2 — site + drive
  const [_siteQuery, setSiteQuery] = useState('');
  const [siteUrl, setSiteUrl] = useState('');
  const [siteResolving, setSiteResolving] = useState(false);
  const [selectedSite, setSelectedSite] = useState<SiteSelection | null>(null);
  const [drives, setDrives] = useState<MicrosoftDrive[]>([]);
  const [drivesLoading, setDrivesLoading] = useState(false);
  const [selectedDrive, setSelectedDrive] = useState<DriveSelection | null>(null);
  // Step 3 — indexing
  const [siloName, setSiloName] = useState('');
  const [vectorDbType, setVectorDbType] = useState('PGVECTOR');
  const [embeddingServiceId, setEmbeddingServiceId] = useState<number | undefined>(undefined);
  const [fileExtensions, setFileExtensions] = useState<string[]>([]);
  const [embeddingServices, setEmbeddingServices] = useState<EmbeddingService[]>([]);

  // Pre-fill silo name when name changes
  useEffect(() => {
    if (name) setSiloName(`${name} ${t('sharePointWizardPage.defaults.siloSuffix')}`);
  }, [name, t]);

  // Load embedding services when reaching step 3
  useEffect(() => {
    if (step === 2 && appId) {
      apiService
        .getEmbeddingServices(Number(appId))
        .then((data: EmbeddingService[]) => setEmbeddingServices(data || []))
        .catch(() => setEmbeddingServices([]));
    }
  }, [step, appId]);

  // Reset site state when entering step 2
  useEffect(() => {
    if (step !== 1) return;
    setSiteUrl('');
    setSiteQuery('');
    setSelectedSite(null);
    setSelectedDrive(null);
    setDrives([]);
  }, [step]);

  async function handleResolveSite() {
    if (!siteUrl.trim()) return;
    setSiteResolving(true);
    setError(null);
    setSelectedSite(null);
    setSelectedDrive(null);
    setDrives([]);
    try {
      const site = await sharepointApi.resolveSite({ ...creds, site_url: siteUrl.trim() });
      setSelectedSite({ site_id: site.id, site_name: site.name, site_url: site.web_url });
      setDrivesLoading(true);
      const ds = await sharepointApi.listDrives({ ...creds, site_id: site.id });
      setDrives(ds);
    } catch (err: any) {
      setError(err?.message ?? t('sharePointWizardPage.errors.siteNotFound'));
    } finally {
      setSiteResolving(false);
      setDrivesLoading(false);
    }
  }


  async function handleNext() {
    setError(null);

    if (step === 0) {
      // Validate and test connection
      if (!name.trim() || !creds.tenant_id || !creds.client_id || !creds.client_secret) {
        setError(t('sharePointWizardPage.errors.requiredFields'));
        return;
      }
      setTestingConnection(true);
      try {
        const result = await sharepointApi.testConnection(creds);
        if (!result.ok) {
          setError(result.error ?? t('sharePointWizardPage.errors.connectionFailed'));
          return;
        }
        setStep(1);
      } catch (err: any) {
        setError(err?.message ?? t('sharePointWizardPage.errors.connectionFailedCredentials'));
      } finally {
        setTestingConnection(false);
      }
      return;
    }

    if (step === 1) {
      if (!selectedSite || !selectedDrive) {
        setError(t('sharePointWizardPage.errors.siteAndDriveRequired'));
        return;
      }
      setStep(2);
      return;
    }

    if (step === 2) {
      // Submit
      if (!siloName.trim()) {
        setError(t('sharePointWizardPage.errors.siloNameRequired'));
        return;
      }
      setSubmitting(true);
      try {
        await sharepointApi.createSource(Number(appId), {
          name,
          description: description || undefined,
          ...creds,
          site_id: selectedSite!.site_id,
          site_name: selectedSite!.site_name,
          site_url: selectedSite!.site_url,
          drive_id: selectedDrive!.drive_id,
          drive_name: selectedDrive!.drive_name,
          silo_name: siloName,
          vector_db_type: vectorDbType,
          embedding_service_id: embeddingServiceId,
          file_extension_filters: fileExtensions.length > 0 ? fileExtensions : undefined,
        });
        navigate(`/apps/${appId}/sharepoint`);
      } catch (err: any) {
        setError(err?.message ?? t('sharePointWizardPage.errors.createFailed'));
      } finally {
        setSubmitting(false);
      }
    }
  }

  function handleBack() {
    setError(null);
    setStep((s) => Math.max(0, s - 1));
  }

  const nextLabel =
    step === 0
      ? testingConnection
        ? t('sharePointWizardPage.actions.testing')
        : t('sharePointWizardPage.actions.testAndNext')
      : step === 2
        ? submitting
          ? t('sharePointWizardPage.actions.creating')
          : t('sharePointWizardPage.actions.create')
        : t('sharePointWizardPage.actions.next');

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <Title
        variant="titPrincipal"
        titulo={t('sharePointWizardPage.title')}
        subtitulo={t('sharePointWizardPage.subtitle')}
      />

      {error && (
        <Alert
          type="error"
          title={t('sharePointWizardPage.errors.title')}
          message={error}
          onDismiss={() => setError(null)}
          className="mb-4"
        />
      )}

      <div className="min-h-[420px] flex flex-col">
        <StepperContainer
          steps={wizardSteps}
          currentStep={step}
          onNext={() => { void handleNext(); }}
          onBack={handleBack}
          onCancel={() => navigate(`/apps/${appId}/sharepoint`)}
          nextLabel={nextLabel}
          backLabel={t('sharePointWizardPage.actions.back')}
          cancelLabel={t('sharePointWizardPage.actions.cancel')}
          submittingLabel={t('sharePointWizardPage.actions.importing')}
          nextDisabled={testingConnection || submitting}
          isSubmitting={testingConnection || submitting}
        >
          {/* -------- Step 1: Credentials -------- */}
          {step === 0 && (
            <div className="space-y-4 py-2">
              <FormField
                label={t('sharePointWizardPage.fields.sourceName')}
                id="source-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder={t('sharePointWizardPage.placeholders.sourceName')}
              />
              <FormTextArea
                label={t('sharePointWizardPage.fields.description')}
                id="source-description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                rows={2}
                placeholder={t('sharePointWizardPage.placeholders.description')}
              />
              <div className="grid grid-cols-2 gap-3">
                <FormField
                  label={t('sharePointWizardPage.fields.tenantId')}
                  id="tenant-id"
                  value={creds.tenant_id}
                  onChange={(e) => setCreds({ ...creds, tenant_id: e.target.value })}
                  placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
                />
                <FormField
                  label={t('sharePointWizardPage.fields.clientId')}
                  id="client-id"
                  value={creds.client_id}
                  onChange={(e) => setCreds({ ...creds, client_id: e.target.value })}
                  placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
                />
              </div>
              <FormField
                label={t('sharePointWizardPage.fields.clientSecret')}
                id="client-secret"
                type="password"
                value={creds.client_secret}
                onChange={(e) => setCreds({ ...creds, client_secret: e.target.value })}
                placeholder={t('sharePointWizardPage.placeholders.clientSecret')}
              />
            </div>
          )}

          {/* -------- Step 2: Site + Drive -------- */}
          {step === 1 && (
            <div className="space-y-4 py-2">
              <div>
                <div className="flex items-end gap-2">
                  <FormField
                    label={t('sharePointWizardPage.fields.siteUrl')}
                    id="sharepoint-site-url"
                    value={siteUrl}
                    onChange={(e) => { setSiteUrl(e.target.value); setSelectedSite(null); setDrives([]); }}
                    onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); void handleResolveSite(); } }}
                    placeholder={t('sharePointWizardPage.placeholders.siteUrl')}
                    className="flex-1"
                    inputClassName="flex-1"
                  />
                  <ButtonApp
                    label={t('sharePointWizardPage.actions.load')}
                    onClick={() => { void handleResolveSite(); }}
                    disabled={!siteUrl.trim()}
                    loading={siteResolving}
                    size="control"
                  />
                </div>
                <p className="text-xs text-fg-secondary dark:text-fg-secondary-dark mt-1">
                  {t('sharePointWizardPage.help.siteUrl')}
                </p>
              </div>

              {selectedSite && (
                <Alert
                  type="success"
                  title={selectedSite.site_name}
                  message={<span className="block truncate">{selectedSite.site_url}</span>}
                />
              )}

              {selectedSite && (
                <div>
                  <label className="block text-sm font-medium text-fg dark:text-fg-dark mb-1">
                    {t('sharePointWizardPage.fields.drive')} <span className="text-error dark:text-error-dark">*</span>
                  </label>
                  {drivesLoading ? (
                    <div className="flex items-center gap-2 text-sm text-fg-tertiary dark:text-fg-tertiary-dark">
                      <Spinner size="sm" tone="muted" /> {t('sharePointWizardPage.states.loadingDrives')}
                    </div>
                  ) : drives.length === 0 ? (
                    <p className="text-sm text-fg-secondary dark:text-fg-secondary-dark">{t('sharePointWizardPage.states.noDrives')}</p>
                  ) : (
                    <div className="border border-line dark:border-line-dark rounded-md divide-y divide-line dark:divide-line-dark">
                      {drives.map((drive) => (
                        <div key={drive.id} className={`flex items-center gap-3 px-3 py-2 transition-colors ${
                          selectedDrive?.drive_id === drive.id
                            ? 'bg-surface-tint dark:bg-surface-tint-dark'
                            : 'hover:bg-surface-tint dark:hover:bg-surface-tint-dark'
                        }`}>
                          <FormRadio
                            label={drive.name}
                            checked={selectedDrive?.drive_id === drive.id}
                            onChange={() => setSelectedDrive({ drive_id: drive.id, drive_name: drive.name })}
                            className="flex items-center gap-3 cursor-pointer text-sm"
                          />
                          {drive.drive_type && (
                            <span className="text-xs text-fg-tertiary dark:text-fg-tertiary-dark">({drive.drive_type})</span>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* -------- Step 3: Indexing config -------- */}
          {step === 2 && (
            <div className="space-y-4 py-2">
              <div>
                <FormField
                  label={t('sharePointWizardPage.fields.siloName')}
                  id="silo-name"
                  value={siloName}
                  onChange={(e) => setSiloName(e.target.value)}
                />
                <p className="text-xs text-fg-secondary dark:text-fg-secondary-dark mt-1">
                  {t('sharePointWizardPage.help.siloName')}
                </p>
              </div>

              <div>
                <FormSelect
                  label={t('sharePointWizardPage.fields.embeddingService')}
                  id="sharepoint-embedding-service"
                  value={embeddingServiceId ?? ''}
                  onChange={(e) =>
                    setEmbeddingServiceId(e.target.value ? Number(e.target.value) : undefined)
                  }
                  options={[
                    { value: '', label: t('sharePointWizardPage.options.defaultEmbedding') },
                    ...selectableServiceOptions(embeddingServices, undefined).map((service) => ({
                      value: service.service_id,
                      label: serviceOptionLabel(service),
                    })),
                  ]}
                  ariaDescribedBy={serviceStatusId(embeddingServices, embeddingServiceId, 'sharepoint-embedding-service')}
                />
                <ServiceOptionStatus
                  options={embeddingServices}
                  selectedId={embeddingServiceId}
                  selectId="sharepoint-embedding-service"
                />
              </div>

              <FormSelect
                label={t('sharePointWizardPage.fields.vectorDatabase')}
                id="vector-database"
                value={vectorDbType}
                onChange={(e) => setVectorDbType(e.target.value)}
                options={[
                  { value: 'PGVECTOR', label: t('sharePointWizardPage.options.pgvector') },
                  { value: 'QDRANT', label: t('sharePointWizardPage.options.qdrant') },
                ]}
              />

              <div>
                <label className="block text-sm font-medium text-fg-secondary dark:text-fg-secondary-dark mb-1">
                  {t('sharePointWizardPage.fields.fileExtensionFilters')}
                </label>
                <TagInput
                  tags={fileExtensions}
                  onChange={setFileExtensions}
                  maxTags={20}
                  placeholder={t('sharePointWizardPage.placeholders.fileExtensions')}
                />
                <p className="text-xs text-fg-tertiary dark:text-fg-tertiary-dark mt-1">
                  {t('sharePointWizardPage.help.fileExtensions')}
                </p>
              </div>
            </div>
          )}
        </StepperContainer>
      </div>
    </div>
  );
}

export default SharePointWizardPage;
