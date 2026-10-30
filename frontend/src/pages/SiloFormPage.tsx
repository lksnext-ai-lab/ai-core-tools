import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { apiService } from '../services/api';
import { useApiMutation } from '../hooks/useApiMutation';
import { errorMessage } from '../constants/messages';
import SiloForm from '../components/forms/SiloForm';
import Title from '../components/ui/Title';
import { LoadingState } from '../components/ui/LoadingState';
import Alert from '../components/ui/Alert';
import type { ServiceLifecycleWarning } from '../types/services';
import ServiceLifecycleAlert from '../components/services/ServiceLifecycleAlert';

// Define the Silo type
interface VectorDbOption {
  code: string;
  label: string;
}

interface Silo {
  silo_id: number;
  name: string;
  type?: string;
  created_at?: string;
  docs_count: number;
  description?: string;
  vector_db_type?: string;
  metadata_definition_id?: number;
  embedding_service_id?: number;
  output_parsers?: { parser_id: number; name: string }[];
  embedding_services?: { service_id: number; name: string }[];
  vector_db_options?: VectorDbOption[];
  transcription_service_id?: number | null;
  video_ai_service_id?: number | null;
  ai_services?: { service_id: number; name: string; supports_video?: boolean }[];
  lifecycle_warnings?: ServiceLifecycleWarning[];
}

function SiloFormPage() {
  const { t } = useTranslation('common');
  const { appId, siloId } = useParams();
  const navigate = useNavigate();
  const mutate = useApiMutation();
  const [silo, setSilo] = useState<Silo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const isEditing = siloId !== undefined && siloId !== 'new';

  // Load silo data if editing
  useEffect(() => {
    if (!appId) {
      setLoading(false);
      return;
    }

    const currentSiloId = isEditing && siloId ? Number.parseInt(siloId, 10) : 0;
    void loadSilo(currentSiloId);
  }, [appId, siloId, isEditing]);

  async function loadSilo(targetSiloId: number) {
    if (!appId) {
      setLoading(false);
      return;
    }

    try {
      setLoading(true);
      setError(null);
      const response = await apiService.getSilo(Number.parseInt(appId, 10), targetSiloId);
      setSilo(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('siloFormPage.loadFailed'));
      console.error('Error loading silo:', err);
    } finally {
      setLoading(false);
    }
  }

  async function handleSubmit(formData: any) {
    if (!appId) return;

    const result = await mutate(
      () =>
        isEditing && siloId
          ? apiService.updateSilo(Number.parseInt(appId), Number.parseInt(siloId), formData)
          : apiService.createSilo(Number.parseInt(appId), formData),
      {
        loading: isEditing ? t('siloFormPage.updating') : t('siloFormPage.creating'),
        success: isEditing ? t('siloFormPage.updated') : t('siloFormPage.created'),

        
        error: (err) => errorMessage(err, t('siloFormPage.saveFailed')),
      },
    );

    if (result !== undefined) {
      navigate(`/apps/${appId}/silos`);
    }
  }

  function handleCancel() {
    navigate(`/apps/${appId}/silos`);
  }
  
  if (loading) {
    return (
      <div className="mx-auto max-w-4xl space-y-6">
        {/* Page Header */}
        <div className="flex items-center justify-between">
          <Title variant="titSecundario" titulo={isEditing ? t('siloFormPage.title.edit') : t('siloFormPage.title.create')}
            subtitulo={isEditing 
                ? t('siloFormPage.subtitle.edit')
                : t('siloFormPage.subtitle.create')
            }
          />
        </div>

        <LoadingState variant="page" message={t('siloFormPage.loading')} />
      </div>
    );
  }

  if (error) {
    return (
      <div className="mx-auto max-w-4xl space-y-6">
        {/* Page Header */}
        <div className="flex items-center justify-between">
              <Title variant="titSecundario" titulo={isEditing ? t('siloFormPage.title.edit') : t('siloFormPage.title.create')}  subtitulo={isEditing
                ? t('siloFormPage.subtitle.edit')
                : t('siloFormPage.subtitle.create')
            }
          />
        </div>

        <Alert
          type="error"
          title={t('siloFormPage.loadErrorTitle')}
          message={(
            <>
              {error}
              <button type="button" onClick={() => navigate(`/apps/${appId}/silos`)} className="mt-2 block underline">
                {t('siloFormPage.backToSilos')}
              </button>
            </>
          )}
        />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      {/* Page Header */}
        <Title variant="titSecundario" titulo={isEditing ? t('siloFormPage.title.edit') : t('siloFormPage.title.create')}  subtitulo={isEditing
          ? t('siloFormPage.subtitle.edit')
          : t('siloFormPage.subtitle.create')
            }
          />


      {silo && <ServiceLifecycleAlert warnings={silo.lifecycle_warnings} variant="full" />}

      {/* Silo Form */}
      <SiloForm
        silo={silo || undefined}
        onSubmit={handleSubmit}
        onCancel={handleCancel}
      />
    </div>
  );
}

export default SiloFormPage; 