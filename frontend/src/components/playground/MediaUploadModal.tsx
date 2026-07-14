import { useState } from 'react';
import { FolderOpen, Tv } from 'lucide-react';
import Modal from '../ui/Modal';
import { apiService } from '../../services/api';

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

  const handleClose = () => {
    setMediaFiles([]);
    setYoutubeUrl('');
    setUploading(false);
    setErrorMessage('');
    onClose();
  };

  const handleUpload = async () => {
    setUploading(true);
    setErrorMessage('');

    try {
      // Processing configuration (services, language, chunking) is defined at
      // the agent level, so the upload only needs the file or URL.
      if (uploadType === 'file' && mediaFiles.length > 0) {
        await apiService.uploadPlaygroundMedia(appId, agentId, sessionId, mediaFiles);
      } else if (uploadType === 'youtube' && youtubeUrl) {
        await apiService.addPlaygroundYouTube(appId, agentId, sessionId, youtubeUrl);
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

  const canUpload =
    uploadType === 'file' ? mediaFiles.length > 0 : !!youtubeUrl.trim();

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

        <p className="text-xs text-gray-500 dark:text-gray-400">
          Transcription, language and chunking settings are configured on the agent.
        </p>

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
