import { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { RefreshCw } from 'lucide-react';
import { StepperContainer } from '../components/ui/Stepper';
import type { StepDefinition } from '../components/ui/Stepper';
import { TagInput } from '../components/ui/TagInput';
import Alert from '../components/ui/Alert';
import { sharepointApi } from '../services/sharepoint';
import { apiService } from '../services/api';
import type { MicrosoftSite, MicrosoftDrive } from '../types/sharepoint';

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

interface EmbeddingService {
  service_id: number;
  name: string;
}

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
  const [siteQuery, setSiteQuery] = useState('');
  const [sites, setSites] = useState<MicrosoftSite[]>([]);
  const [sitesLoading, setSitesLoading] = useState(false);
  const [selectedSite, setSelectedSite] = useState<SiteSelection | null>(null);
  const [drives, setDrives] = useState<MicrosoftDrive[]>([]);
  const [drivesLoading, setDrivesLoading] = useState(false);
  const [selectedDrive, setSelectedDrive] = useState<DriveSelection | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

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

  // Debounced site search
  useEffect(() => {
    if (step !== 1) return;
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (!siteQuery.trim()) {
      setSites([]);
      return;
    }
    debounceRef.current = setTimeout(async () => {
      setSitesLoading(true);
      try {
        const results = await sharepointApi.searchSites({
          ...creds,
          q: siteQuery,
        });
        setSites(results);
      } catch {
        setSites([]);
      } finally {
        setSitesLoading(false);
      }
    }, 300);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [siteQuery, step]);

  async function handleSelectSite(site: MicrosoftSite) {
    setSelectedSite({
      site_id: site.id,
      site_name: site.name,
      site_url: site.web_url,
    });
    setSelectedDrive(null);
    setDrives([]);
    setDrivesLoading(true);
    try {
      const ds = await sharepointApi.listDrives({ ...creds, site_id: site.id });
      setDrives(ds);
    } catch {
      setDrives([]);
    } finally {
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
    <div className="max-w-2xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Add SharePoint Source</h1>
        <p className="text-gray-600">Connect a Microsoft SharePoint drive to index its documents.</p>
      </div>

      {error && (
        <Alert
          type="error"
          title="Error"
          message={error}
          onDismiss={() => setError(null)}
          className="mb-4"
        />
      )}

      <div className="bg-white rounded-xl border border-gray-200 p-6 min-h-[420px] flex flex-col">
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
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Source Name <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="My SharePoint Source"
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Description</label>
                <textarea
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  rows={2}
                  placeholder="Optional description"
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Tenant ID <span className="text-red-500">*</span>
                  </label>
                  <input
                    type="text"
                    value={creds.tenant_id}
                    onChange={(e) => setCreds({ ...creds, tenant_id: e.target.value })}
                    placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
                    className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Client ID <span className="text-red-500">*</span>
                  </label>
                  <input
                    type="text"
                    value={creds.client_id}
                    onChange={(e) => setCreds({ ...creds, client_id: e.target.value })}
                    placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
                    className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Client Secret <span className="text-red-500">*</span>
                </label>
                <input
                  type="password"
                  value={creds.client_secret}
                  onChange={(e) => setCreds({ ...creds, client_secret: e.target.value })}
                  placeholder="Your Azure app client secret"
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
            </div>
          )}

          {/* -------- Step 2: Site + Drive -------- */}
          {step === 1 && (
            <div className="space-y-4 py-2">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Search SharePoint site <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  value={siteQuery}
                  onChange={(e) => {
                    setSiteQuery(e.target.value);
                    setSelectedSite(null);
                    setSelectedDrive(null);
                  }}
                  placeholder="Type to search sites..."
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
                {sitesLoading && (
                  <div className="flex items-center gap-1 mt-1 text-xs text-gray-500">
                    <RefreshCw className="w-3 h-3 animate-spin" /> Searching...
                  </div>
                )}
                {sites.length > 0 && !selectedSite && (
                  <ul className="mt-1 border border-gray-200 rounded-lg divide-y divide-gray-100 max-h-40 overflow-y-auto">
                    {sites.map((site) => (
                      <li key={site.id}>
                        <button
                          type="button"
                          onClick={() => { void handleSelectSite(site); }}
                          className="w-full text-left px-3 py-2 text-sm hover:bg-blue-50"
                        >
                          <span className="font-medium text-gray-800">{site.name}</span>
                          <span className="ml-2 text-xs text-gray-400">{site.web_url}</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
                {selectedSite && (
                  <p className="mt-1 text-sm text-green-700">
                    Selected: <strong>{selectedSite.site_name}</strong>
                  </p>
                )}
              </div>

              {selectedSite && (
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Choose Drive <span className="text-red-500">*</span>
                  </label>
                  {drivesLoading ? (
                    <div className="flex items-center gap-1 text-xs text-gray-500">
                      <RefreshCw className="w-3 h-3 animate-spin" /> Loading drives...
                    </div>
                  ) : (
                    <div className="space-y-2">
                      {drives.map((drive) => (
                        <label key={drive.id} className="flex items-center gap-2 cursor-pointer">
                          <input
                            type="radio"
                            name="drive"
                            value={drive.id}
                            checked={selectedDrive?.drive_id === drive.id}
                            onChange={() =>
                              setSelectedDrive({ drive_id: drive.id, drive_name: drive.name })
                            }
                            className="text-blue-600"
                          />
                          <span className="text-sm text-gray-800">
                            {drive.name}
                            {drive.drive_type && (
                              <span className="ml-1 text-xs text-gray-400">({drive.drive_type})</span>
                            )}
                          </span>
                        </label>
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
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Silo Name <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  value={siloName}
                  onChange={(e) => setSiloName(e.target.value)}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
                <p className="text-xs text-gray-500 mt-1">
                  A new silo will be created to store the indexed documents.
                </p>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Embedding Service
                </label>
                <select
                  value={embeddingServiceId ?? ''}
                  onChange={(e) =>
                    setEmbeddingServiceId(e.target.value ? Number(e.target.value) : undefined)
                  }
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  <option value="">— Use default —</option>
                  {embeddingServices.map((svc) => (
                    <option key={svc.service_id} value={svc.service_id}>
                      {svc.name}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Vector Database
                </label>
                <select
                  value={vectorDbType}
                  onChange={(e) => setVectorDbType(e.target.value)}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  <option value="PGVECTOR">PGVector (PostgreSQL)</option>
                  <option value="QDRANT">Qdrant</option>
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  File Extension Filters
                </label>
                <TagInput
                  tags={fileExtensions}
                  onChange={setFileExtensions}
                  maxTags={20}
                  placeholder="e.g. pdf, docx — press Enter to add"
                />
                <p className="text-xs text-gray-500 mt-1">
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
