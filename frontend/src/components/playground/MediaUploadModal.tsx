import { useState, useEffect } from 'react';
import { FolderOpen, Tv } from 'lucide-react';
import Modal from '../ui/Modal';
import { apiService } from '../../services/api';

interface AIServiceOption {
  service_id: number;
  name: string;
  provider?: string;
  supports_video?: boolean;
}

interface MediaUploadModalProps {
  isOpen: boolean;
  onClose: () => void;
  appId: number;
  agentId: number;
  sessionId: string;
  onUploadComplete?: () => void;
}

function MediaUploadModal({
  isOpen,
  onClose,
  appId,
  agentId,
  sessionId,
  onUploadComplete,
}: Readonly<MediaUploadModalProps>) {
  const [uploadType, setUploadType] = useState<'file' | 'youtube'>('file');
  const [mediaFiles, setMediaFiles] = useState<File[]>([]);
  const [youtubeUrl, setYoutubeUrl] = useState('');
  const [uploading, setUploading] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');

  // AI service selection
  const [aiServices, setAiServices] = useState<AIServiceOption[]>([]);
  const [transcriptionServiceId, setTranscriptionServiceId] = useState<number | undefined>();
  const [videoAiServiceId, setVideoAiServiceId] = useState<number | undefined>();
  const [servicesLoaded, setServicesLoaded] = useState(false);

  const [mediaConfig, setMediaConfig] = useState({
    forced_language: '',
    chunk_min_duration: 30,
    chunk_max_duration: 120,
    chunk_overlap: 5,
  });

  // Load available AI services when modal opens
  useEffect(() => {
    if (isOpen && !servicesLoaded) {
      loadAIServices();
    }
  }, [isOpen]);

  const loadAIServices = async () => {
    try {
      const services = await apiService.getAIServices(appId);
      setAiServices(services as AIServiceOption[]);

      // Auto-select first service as transcription if available
      if (Array.isArray(services) && services.length > 0) {
        setTranscriptionServiceId((services as AIServiceOption[])[0].service_id);
      }
      setServicesLoaded(true);
    } catch (error) {
      console.error('Error loading AI services:', error);
    }
  };

  const handleClose = () => {
    setMediaFiles([]);
    setYoutubeUrl('');
    setUploading(false);
    setErrorMessage('');
    onClose();
  };

  const handleUpload = async () => {
    if (!transcriptionServiceId) {
      setErrorMessage('Please select a transcription service.');
      return;
    }

    setUploading(true);
    setErrorMessage('');

    try {
      const config = {
        transcription_service_id: transcriptionServiceId,
        video_ai_service_id: videoAiServiceId,
        forced_language: mediaConfig.forced_language || undefined,
        chunk_min_duration: mediaConfig.chunk_min_duration,
        chunk_max_duration: mediaConfig.chunk_max_duration,
        chunk_overlap: mediaConfig.chunk_overlap,
      };

      if (uploadType === 'file' && mediaFiles.length > 0) {
        await apiService.uploadPlaygroundMedia(appId, agentId, sessionId, mediaFiles, config);
      } else if (uploadType === 'youtube' && youtubeUrl) {
        await apiService.addPlaygroundYouTube(appId, agentId, sessionId, youtubeUrl, config);
      }

      onUploadComplete?.();
      handleClose();
    } catch (error) {
      console.error('Error uploading media:', error);
      setErrorMessage(error instanceof Error ? error.message : 'Upload failed');
    } finally {
      setUploading(false);
    }
  };

  const videoCapableServices = aiServices.filter((s) => s.supports_video);

  // Detect if only audio files are selected (no video files)
  const AUDIO_EXTENSIONS = new Set(['.mp3', '.wav', '.m4a', '.ogg', '.flac', '.aac', '.wma']);
  const hasOnlyAudio =
    uploadType === 'file' &&
    mediaFiles.length > 0 &&
    mediaFiles.every((f) => {
      const ext = f.name.slice(f.name.lastIndexOf('.')).toLowerCase();
      return AUDIO_EXTENSIONS.has(ext) || f.type.startsWith('audio/');
    });

  // Clear video AI service when only audio is selected
  useEffect(() => {
    if (hasOnlyAudio && videoAiServiceId) {
      setVideoAiServiceId(undefined);
    }
  }, [hasOnlyAudio]);

  const canUpload =
    !!transcriptionServiceId &&
    (uploadType === 'file' ? mediaFiles.length > 0 : !!youtubeUrl.trim());

  return (
    <Modal isOpen={isOpen} onClose={handleClose} title="Upload Media" size="large">
      <div className="space-y-4">
        {/* Upload Type Tabs */}
        <div className="flex gap-2">
          <button
            onClick={() => setUploadType('file')}
            className={`flex-1 px-4 py-2 rounded text-sm font-medium transition-colors ${
              uploadType === 'file'
                ? 'bg-purple-600 text-white'
                : 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300'
            }`}
          >
            <FolderOpen className="w-4 h-4 inline-block mr-1" /> File Upload
          </button>
          <button
            onClick={() => setUploadType('youtube')}
            className={`flex-1 px-4 py-2 rounded text-sm font-medium transition-colors ${
              uploadType === 'youtube'
                ? 'bg-purple-600 text-white'
                : 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300'
            }`}
          >
            <Tv className="w-4 h-4 inline-block mr-1" /> YouTube URL
          </button>
        </div>

        {/* File Upload */}
        {uploadType === 'file' && (
          <div>
            <label
              htmlFor="pg-media-files-input"
              className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2"
            >
              Select Video/Audio Files
            </label>
            <input
              id="pg-media-files-input"
              type="file"
              multiple
              accept="video/*,audio/*"
              onChange={(e) => setMediaFiles(Array.from(e.target.files || []))}
              className="w-full"
            />
            {mediaFiles.length > 0 && (
              <p className="text-sm text-gray-600 dark:text-gray-400 mt-2">
                {mediaFiles.length} file(s) selected
              </p>
            )}
          </div>
        )}

        {/* YouTube URL */}
        {uploadType === 'youtube' && (
          <div>
            <label
              htmlFor="pg-youtube-url-input"
              className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2"
            >
              YouTube URL
            </label>
            <input
              id="pg-youtube-url-input"
              type="text"
              value={youtubeUrl}
              onChange={(e) => setYoutubeUrl(e.target.value)}
              placeholder="https://youtube.com/watch?v=..."
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md
                         bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
            />
          </div>
        )}

        {/* AI Service Selection */}
        <div className="border-t dark:border-gray-700 pt-4">
          <h3 className="font-medium text-gray-900 dark:text-gray-100 mb-3">AI Services</h3>

          <div className="space-y-3">
            {/* Transcription Service (required) */}
            <div>
              <label
                htmlFor="pg-transcription-service"
                className="block text-sm text-gray-700 dark:text-gray-300 mb-1"
              >
                Transcription Service <span className="text-red-500">*</span>
              </label>
              {aiServices.length === 0 && servicesLoaded ? (
                <p className="text-sm text-red-600">
                  No AI services configured. Add one in the app settings.
                </p>
              ) : (
                <select
                  id="pg-transcription-service"
                  value={transcriptionServiceId ?? ''}
                  onChange={(e) =>
                    setTranscriptionServiceId(e.target.value ? Number(e.target.value) : undefined)
                  }
                  className="w-full px-3 py-2 border dark:border-gray-600 rounded-md text-sm
                             bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                >
                  <option value="">Select a service...</option>
                  {aiServices.map((s) => (
                    <option key={s.service_id} value={s.service_id}>
                      {s.name} ({s.provider})
                    </option>
                  ))}
                </select>
              )}
            </div>

            {/* Video AI Service (optional — hidden for audio-only uploads) */}
            {videoCapableServices.length > 0 && !hasOnlyAudio && (
              <div>
                <label
                  htmlFor="pg-video-ai-service"
                  className="block text-sm text-gray-700 dark:text-gray-300 mb-1"
                >
                  Video Analysis Service (optional)
                </label>
                <select
                  id="pg-video-ai-service"
                  value={videoAiServiceId ?? ''}
                  onChange={(e) =>
                    setVideoAiServiceId(e.target.value ? Number(e.target.value) : undefined)
                  }
                  className="w-full px-3 py-2 border dark:border-gray-600 rounded-md text-sm
                             bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                >
                  <option value="">None (audio only)</option>
                  {videoCapableServices.map((s) => (
                    <option key={s.service_id} value={s.service_id}>
                      {s.name} ({s.provider})
                    </option>
                  ))}
                </select>
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                  Enables multimodal analysis (visual descriptions from video frames)
                </p>
              </div>
            )}
          </div>
        </div>

        {/* Processing Options */}
        <div className="border-t dark:border-gray-700 pt-4">
          <h3 className="font-medium text-gray-900 dark:text-gray-100 mb-3">Processing Options</h3>

          <div className="space-y-3">
            <div>
              <label
                htmlFor="pg-media-language"
                className="block text-sm text-gray-700 dark:text-gray-300 mb-1"
              >
                Language (optional)
              </label>
              <select
                id="pg-media-language"
                value={mediaConfig.forced_language}
                onChange={(e) =>
                  setMediaConfig({ ...mediaConfig, forced_language: e.target.value })
                }
                className="w-full px-3 py-2 border dark:border-gray-600 rounded-md text-sm
                           bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
              >
                <option value="">Auto-detect</option>
                <option value="es">Spanish</option>
                <option value="en">English</option>
                <option value="eu">Basque</option>
                <option value="fr">French</option>
              </select>
            </div>

            <div className="grid grid-cols-3 gap-2">
              <div>
                <label htmlFor="pg-chunk-min" className="block text-xs text-gray-700 dark:text-gray-300 mb-1">
                  Min Chunk (s)
                </label>
                <input
                  id="pg-chunk-min"
                  type="number"
                  value={mediaConfig.chunk_min_duration}
                  onChange={(e) =>
                    setMediaConfig({ ...mediaConfig, chunk_min_duration: Number.parseInt(e.target.value) })
                  }
                  className="w-full px-2 py-1 border dark:border-gray-600 rounded text-sm
                             bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                  min="10"
                  max="60"
                />
              </div>
              <div>
                <label htmlFor="pg-chunk-max" className="block text-xs text-gray-700 dark:text-gray-300 mb-1">
                  Max Chunk (s)
                </label>
                <input
                  id="pg-chunk-max"
                  type="number"
                  value={mediaConfig.chunk_max_duration}
                  onChange={(e) =>
                    setMediaConfig({ ...mediaConfig, chunk_max_duration: Number.parseInt(e.target.value) })
                  }
                  className="w-full px-2 py-1 border dark:border-gray-600 rounded text-sm
                             bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                  min="60"
                  max="300"
                />
              </div>
              <div>
                <label htmlFor="pg-chunk-overlap" className="block text-xs text-gray-700 dark:text-gray-300 mb-1">
                  Overlap (s)
                </label>
                <input
                  id="pg-chunk-overlap"
                  type="number"
                  value={mediaConfig.chunk_overlap}
                  onChange={(e) =>
                    setMediaConfig({ ...mediaConfig, chunk_overlap: Number.parseInt(e.target.value) })
                  }
                  className="w-full px-2 py-1 border dark:border-gray-600 rounded text-sm
                             bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                  min="0"
                  max="20"
                />
              </div>
            </div>
          </div>
        </div>

        {/* Error */}
        {errorMessage && (
          <div className="text-sm text-red-600 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded p-2">
            {errorMessage}
          </div>
        )}

        {/* Actions */}
        <div className="flex justify-end gap-3 pt-4 border-t dark:border-gray-700">
          <button
            onClick={handleClose}
            className="px-4 py-2 text-gray-600 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-200"
          >
            Cancel
          </button>
          <button
            onClick={handleUpload}
            disabled={!canUpload || uploading}
            className="px-4 py-2 bg-purple-600 text-white rounded-md hover:bg-purple-700
                       disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {uploading ? 'Uploading...' : 'Upload'}
          </button>
        </div>
      </div>
    </Modal>
  );
}

export default MediaUploadModal;
