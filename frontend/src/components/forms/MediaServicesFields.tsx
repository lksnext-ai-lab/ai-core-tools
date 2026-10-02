export interface MediaAIServiceOption {
  service_id: number;
  name: string;
  supports_video?: boolean;
}

interface Props {
  aiServices: MediaAIServiceOption[];
  transcriptionServiceId?: number | null;
  videoServiceId?: number | null;
  onChange: (field: 'transcription_service_id' | 'video_ai_service_id', value: number | null) => void;
  /** Wording: repositories configure the silo they create; silos configure themselves. */
  scope: 'repository' | 'silo';
  disabled?: boolean;
}

const selectClass =
  'w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:bg-gray-100';

/**
 * Transcription + video-analysis services used to index video/audio.
 * Stored on the silo, so a repository and its silo share the same configuration.
 */
export function MediaServicesFields({
  aiServices, transcriptionServiceId, videoServiceId, onChange, scope, disabled = false,
}: Readonly<Props>) {
  if (aiServices.length === 0) return null;
  const videoServices = aiServices.filter((s) => s.supports_video);
  const parse = (value: string) => (value ? Number.parseInt(value, 10) : null);

  return (
    <>
      <div>
        <label htmlFor="transcription_service_id" className="block text-sm font-medium text-gray-700 mb-2">
          Transcription Service (Whisper)
        </label>
        <select
          id="transcription_service_id"
          value={transcriptionServiceId ?? ''}
          disabled={disabled}
          onChange={(e) => onChange('transcription_service_id', parse(e.target.value))}
          className={selectClass}
          aria-describedby="transcription_service_id_help"
        >
          <option value="">None (video and audio are not indexed)</option>
          {aiServices.map((service) => (
            <option key={service.service_id} value={service.service_id}>{service.name}</option>
          ))}
        </select>
        <p id="transcription_service_id_help" className="text-sm text-gray-500 mt-1">
          {scope === 'repository'
            ? 'Transcribes the video and audio uploaded to this repository. Stored on its silo.'
            : 'Optional. Needed to index video and audio into this silo (for example through the public API).'}
        </p>
      </div>

      {videoServices.length > 0 && (
        <div>
          <label htmlFor="video_ai_service_id" className="block text-sm font-medium text-gray-700 mb-2">
            Video Analysis Service (Gemini)
          </label>
          <select
            id="video_ai_service_id"
            value={videoServiceId ?? ''}
            disabled={disabled}
            onChange={(e) => onChange('video_ai_service_id', parse(e.target.value))}
            className={selectClass}
            aria-describedby="video_ai_service_id_help"
          >
            <option value="">None (no visual analysis)</option>
            {videoServices.map((service) => (
              <option key={service.service_id} value={service.service_id}>{service.name}</option>
            ))}
          </select>
          <p id="video_ai_service_id_help" className="text-sm text-gray-500 mt-1">
            Optional. Adds a description of what is seen in the video to each transcribed chunk.
          </p>
        </div>
      )}
    </>
  );
}
