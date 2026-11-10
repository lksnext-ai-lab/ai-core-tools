import { useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { FolderOpen } from 'lucide-react';
import Modal from '../ui/Modal';
import ButtonApp from '../ui/ButtonApp';
import { SegmentedTabs } from '../ui/SegmentedTabs';
import { FormField } from '../ui/FormField';
import Alert from '../ui/Alert';
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
  const { t } = useTranslation('common');
  const [uploadType, setUploadType] = useState<'file' | 'youtube'>('file');
  const [mediaFiles, setMediaFiles] = useState<File[]>([]);
  const mediaFileInputRef = useRef<HTMLInputElement>(null);
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
      setErrorMessage(error instanceof Error ? error.message : t('playgroundMedia.uploadFailed'));
    } finally {
      setUploading(false);
    }
  };

  const canUpload =
    uploadType === 'file' ? mediaFiles.length > 0 : !!youtubeUrl.trim();

  return (
    <Modal isOpen={isOpen} onClose={handleClose} title={t('playgroundMedia.title')} size="large">
      <div className="space-y-4">
        {/* Upload Type Tabs */}
        <SegmentedTabs
          tabs={[
            { id: 'file', label: t('playgroundMedia.fileUpload') },
            { id: 'youtube', label: t('playgroundMedia.youtubeUrl') },
          ]}
          activeTab={uploadType}
          onChange={setUploadType}
          ariaLabel={t('playgroundMedia.title')}
        />

        {/* File Upload */}
        {uploadType === 'file' && (
          <div>
            <ButtonApp
              label={t('playgroundMedia.selectFiles')}
              onClick={() => mediaFileInputRef.current?.click()}
              variant="primary"
              size="medium"
              icon={<FolderOpen className="w-4 h-4" aria-hidden="true" />}
            />
            <input
              ref={mediaFileInputRef}
              id="pg-media-files-input"
              type="file"
              multiple
              accept="video/*,audio/*"
              onChange={(e) => setMediaFiles(Array.from(e.target.files || []))}
              className="hidden"
            />
            {mediaFiles.length > 0 && (
              <p className="text-sm text-fg-secondary dark:text-fg-secondary-dark mt-2">
                {t('playgroundMedia.selectedFiles', { count: mediaFiles.length })}
              </p>
            )}
          </div>
        )}

        {/* YouTube URL */}
        {uploadType === 'youtube' && (
          <div>
            <FormField
              id="pg-youtube-url-input"
              type="text"
              label="YouTube URL"
              value={youtubeUrl}
              onChange={(e) => setYoutubeUrl(e.target.value)}
              placeholder="https://youtube.com/watch?v=..."
            />
          </div>
        )}

        <p className="text-xs text-fg-tertiary dark:text-fg-tertiary-dark">
          {t('playgroundMedia.configurationNote')}
        </p>

        {/* Error */}
        {errorMessage && (
          <Alert type="error" message={errorMessage} />
        )}

        {/* Actions */}
        <div className="flex justify-end gap-3 pt-4 border-t border-line dark:border-line-dark">
          <ButtonApp
            label={t('cancel')}
            onClick={handleClose}
            variant="secondary"
            size="medium"
          />
          <ButtonApp
            label={uploading ? t('playgroundMedia.uploading') : t('playgroundMedia.upload')}
            onClick={handleUpload}
            disabled={!canUpload}
            loading={uploading}
            variant="primary"
            size="medium"
          />
        </div>
      </div>
    </Modal>
  );
}

export default MediaUploadModal;
