import { ServiceOptionStatus, serviceStatusId } from '../ui/ServiceOptionStatus';
import type { ServiceOptionLike } from '../../utils/serviceLifecycle';
import { selectableServiceOptions, serviceOptionLabel } from '../../utils/serviceLifecycle';
import { FormSelect } from '../ui/FormField';

export interface MediaAIServiceOption extends ServiceOptionLike {
  supports_video?: boolean;
}

interface Props {
  aiServices: MediaAIServiceOption[];
  transcriptionServiceId?: number | null;
  videoServiceId?: number | null;
  /** Values saved on the loaded entity (D-4): a retired service stays selectable only if it is one of these. */
  savedTranscriptionServiceId?: number | null;
  savedVideoServiceId?: number | null;
  onChange: (field: 'transcription_service_id' | 'video_ai_service_id', value: number | null) => void;
  /** Wording: repositories configure the silo they create; silos configure themselves. */
  scope: 'repository' | 'silo';
  disabled?: boolean;
}

/**
 * Transcription + video-analysis services used to index video/audio.
 * Stored on the silo, so a repository and its silo share the same configuration.
 */
export function MediaServicesFields({
  aiServices, transcriptionServiceId, videoServiceId, savedTranscriptionServiceId, savedVideoServiceId, onChange, scope, disabled = false,
}: Readonly<Props>) {
  if (aiServices.length === 0) return null;
  const videoServices = aiServices.filter((s) => s.supports_video);
  const transcriptionDescribedBy = [
    'transcription_service_id_help',
    serviceStatusId(aiServices, transcriptionServiceId, 'transcription_service_id'),
  ].filter(Boolean).join(' ');
  const videoDescribedBy = [
    'video_ai_service_id_help',
    serviceStatusId(videoServices, videoServiceId, 'video_ai_service_id'),
  ].filter(Boolean).join(' ');
  const parse = (value: string) => (value ? Number.parseInt(value, 10) : null);

  return (
    <>
      <div>
        <FormSelect
          label="Transcription Service (Whisper)"
          id="transcription_service_id"
          value={transcriptionServiceId ?? ''}
          disabled={disabled}
          onChange={(e) => onChange('transcription_service_id', parse(e.target.value))}
          ariaDescribedBy={transcriptionDescribedBy}
          options={[
            { value: '', label: 'None (video and audio are not indexed)' },
            ...selectableServiceOptions(aiServices, savedTranscriptionServiceId).map((service) => ({
              value: service.service_id,
              label: serviceOptionLabel(service),
            })),
          ]}
          labelClassName="block text-sm font-medium text-fg dark:text-fg-dark mb-1"
        />
        <ServiceOptionStatus selectId="transcription_service_id" options={aiServices} selectedId={transcriptionServiceId} />
        <p id="transcription_service_id_help" className="mt-1 text-xs text-fg-tertiary dark:text-fg-tertiary-dark">
          {scope === 'repository'
            ? 'Transcribes the video and audio uploaded to this repository. Stored on its silo.'
            : 'Optional. Needed to index video and audio into this silo (for example through the public API).'}
        </p>
      </div>

      {videoServices.length > 0 && (
        <div>
          <FormSelect
            label="Video Analysis Service (Gemini)"
            id="video_ai_service_id"
            value={videoServiceId ?? ''}
            disabled={disabled}
            onChange={(e) => onChange('video_ai_service_id', parse(e.target.value))}
            ariaDescribedBy={videoDescribedBy}
            options={[
              { value: '', label: 'None (no visual analysis)' },
              ...selectableServiceOptions(videoServices, savedVideoServiceId).map((service) => ({
                value: service.service_id,
                label: serviceOptionLabel(service),
              })),
            ]}
            labelClassName="block text-sm font-medium text-fg dark:text-fg-dark mb-1"
          />
          <ServiceOptionStatus selectId="video_ai_service_id" options={videoServices} selectedId={videoServiceId} />
          <p id="video_ai_service_id_help" className="mt-1 text-xs text-fg-tertiary dark:text-fg-tertiary-dark">
            Optional. Adds a description of what is seen in the video to each transcribed chunk.
          </p>
        </div>
      )}
    </>
  );
}
