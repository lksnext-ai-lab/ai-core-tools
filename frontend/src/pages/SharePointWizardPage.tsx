import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
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

const WIZARD_STEPS: StepDefinition[] = [
  { id: 'connect', label: 'Connect' },
  { id: 'drive', label: 'Choose Drive' },
  { id: 'indexing', label: 'Indexing' },
];

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
    if (name) setSiloName(`${name} Silo`);
  }, [name]);

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
      setError(err?.message ?? 'Site not found. Check the URL and permissions.');
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
        setError('Please fill in all required fields.');
        return;
      }
      setTestingConnection(true);
      try {
        const result = await sharepointApi.testConnection(creds);
        if (!result.ok) {
          setError(result.error ?? 'Connection test failed.');
          return;
        }
        setStep(1);
      } catch (err: any) {
        setError(err?.message ?? 'Connection test failed. Check your credentials.');
      } finally {
        setTestingConnection(false);
      }
      return;
    }

    if (step === 1) {
      if (!selectedSite || !selectedDrive) {
        setError('Please select a site and a drive.');
        return;
      }
      setStep(2);
      return;
    }

    if (step === 2) {
      // Submit
      if (!siloName.trim()) {
        setError('Please provide a silo name.');
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
        setError(err?.message ?? 'Failed to create SharePoint source.');
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
        ? 'Testing...'
        : 'Test & Next'
      : step === 2
        ? submitting
          ? 'Creating...'
          : 'Create'
        : 'Next';

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <Title variant="titPrincipal" titulo="Add SharePoint Source" subtitulo="Connect a Microsoft SharePoint drive to index its documents." />

      {error && (
        <Alert
          type="error"
          title="Error"
          message={error}
          onDismiss={() => setError(null)}
          className="mb-4"
        />
      )}

      <div className="min-h-[420px] flex flex-col">
        <StepperContainer
          steps={WIZARD_STEPS}
          currentStep={step}
          onNext={() => { void handleNext(); }}
          onBack={handleBack}
          onCancel={() => navigate(`/apps/${appId}/sharepoint`)}
          nextLabel={nextLabel}
          nextDisabled={testingConnection || submitting}
          isSubmitting={testingConnection || submitting}
        >
          {/* -------- Step 1: Credentials -------- */}
          {step === 0 && (
            <div className="space-y-4 py-2">
              <FormField
                label="Source Name *"
                id="source-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="My SharePoint Source"
              />
              <FormTextArea
                label="Description"
                id="source-description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                rows={2}
                placeholder="Optional description"
              />
              <div className="grid grid-cols-2 gap-3">
                <FormField
                  label="Tenant ID *"
                  id="tenant-id"
                  value={creds.tenant_id}
                  onChange={(e) => setCreds({ ...creds, tenant_id: e.target.value })}
                  placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
                />
                <FormField
                  label="Client ID *"
                  id="client-id"
                  value={creds.client_id}
                  onChange={(e) => setCreds({ ...creds, client_id: e.target.value })}
                  placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
                />
              </div>
              <FormField
                label="Client Secret *"
                id="client-secret"
                type="password"
                value={creds.client_secret}
                onChange={(e) => setCreds({ ...creds, client_secret: e.target.value })}
                placeholder="Your Azure app client secret"
              />
            </div>
          )}

          {/* -------- Step 2: Site + Drive -------- */}
          {step === 1 && (
            <div className="space-y-4 py-2">
              <div>
                <div className="flex gap-2">
                  <FormField
                    label="SharePoint Site URL *"
                    id="sharepoint-site-url"
                    value={siteUrl}
                    onChange={(e) => { setSiteUrl(e.target.value); setSelectedSite(null); setDrives([]); }}
                    onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); void handleResolveSite(); } }}
                    placeholder="https://yourtenant.sharepoint.com/sites/Marketing"
                    className="flex-1"
                    inputClassName="flex-1"
                  />
                  <ButtonApp
                    label="Load"
                    onClick={() => { void handleResolveSite(); }}
                    disabled={!siteUrl.trim()}
                    loading={siteResolving}
                    size="control"
                  />
                </div>
                <p className="text-xs text-gray-500 mt-1">
                  Enter the URL of your SharePoint site, then click Load.
                </p>
              </div>

              {selectedSite && (
                <div className="rounded-lg bg-green-50 border border-green-200 px-3 py-2 text-sm">
                  <span className="font-medium text-green-800">{selectedSite.site_name}</span>
                  <span className="block text-xs text-green-600 truncate">{selectedSite.site_url}</span>
                </div>
              )}

              {selectedSite && (
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Drive <span className="text-red-500">*</span>
                  </label>
                  {drivesLoading ? (
                    <div className="flex items-center gap-2 text-sm text-fg-tertiary dark:text-fg-tertiary-dark">
                      <Spinner size="sm" tone="muted" /> Loading drives...
                    </div>
                  ) : drives.length === 0 ? (
                    <p className="text-sm text-gray-500">No drives found for this site.</p>
                  ) : (
                    <div className="border border-gray-200 rounded-lg divide-y divide-gray-100">
                      {drives.map((drive) => (
                        <div key={drive.id} className={`flex items-center gap-3 px-3 py-2 transition-colors ${
                          selectedDrive?.drive_id === drive.id ? 'bg-blue-50' : 'hover:bg-gray-50'
                        }`}>
                          <FormRadio
                            label={drive.name}
                            checked={selectedDrive?.drive_id === drive.id}
                            onChange={() => setSelectedDrive({ drive_id: drive.id, drive_name: drive.name })}
                            className="flex items-center gap-3 cursor-pointer"
                          />
                          {drive.drive_type && (
                            <span className="text-xs text-gray-400">({drive.drive_type})</span>
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
                  label="Silo Name *"
                  id="silo-name"
                  value={siloName}
                  onChange={(e) => setSiloName(e.target.value)}
                />
                <p className="text-xs text-gray-500 mt-1">
                  A new silo will be created to store the indexed documents.
                </p>
              </div>

              <div>
                <FormSelect
                  label="Embedding Service"
                  id="sharepoint-embedding-service"
                  value={embeddingServiceId ?? ''}
                  onChange={(e) =>
                    setEmbeddingServiceId(e.target.value ? Number(e.target.value) : undefined)
                  }
                  options={[
                    { value: '', label: '— Use default —' },
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
                label="Vector Database"
                id="vector-database"
                value={vectorDbType}
                onChange={(e) => setVectorDbType(e.target.value)}
                options={[
                  { value: 'PGVECTOR', label: 'PGVector (PostgreSQL)' },
                  { value: 'QDRANT', label: 'Qdrant' },
                ]}
              />

              <div>
                <label className="block text-sm font-medium text-fg-secondary dark:text-fg-secondary-dark mb-1">
                  File Extension Filters
                </label>
                <TagInput
                  tags={fileExtensions}
                  onChange={setFileExtensions}
                  maxTags={20}
                  placeholder="e.g. pdf, docx — press Enter to add"
                />
                <p className="text-xs text-fg-tertiary dark:text-fg-tertiary-dark mt-1">
                  Leave empty to index all supported file types.
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
