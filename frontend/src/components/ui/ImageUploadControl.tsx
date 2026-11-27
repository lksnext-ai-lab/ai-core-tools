import { useRef, useState } from 'react';
import type { ChangeEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { Camera, Trash2 } from 'lucide-react';

import ButtonApp from './ButtonApp';
import { ApiError } from '../../services/api';

// Same limits as the backend (backend/utils/image_normalization.py), checked first to skip a doomed upload.
export const IMAGE_ACCEPTED_TYPES = ['image/png', 'image/jpeg', 'image/webp', 'image/gif'];
export const IMAGE_MAX_BYTES = 5 * 1024 * 1024;

const ERROR_KEYS: Record<string, string> = {
  IMAGE_TOO_LARGE: 'imageUpload.tooLarge',
  IMAGE_INVALID_TYPE: 'imageUpload.invalidType',
};

function errorCode(err: unknown): string | undefined {
  if (!(err instanceof ApiError) || !err.detail || typeof err.detail !== 'object') return undefined;
  const code = (err.detail as Record<string, unknown>)['code'];
  return typeof code === 'string' ? code : undefined;
}

export interface ImageUploadControlProps {
  readonly hasImage: boolean;
  /** Accessible name of the file input, e.g. "Choose a profile picture". */
  readonly inputLabel: string;
  readonly onUpload: (file: File) => Promise<void>;
  readonly onRemove: () => Promise<void>;
  readonly onSuccess: (message: string) => void;
  readonly onError: (message: string) => void;
  readonly disabled?: boolean;
  readonly className?: string;
}

/** Upload / change / remove buttons for a stored picture (user avatar, App image), with the format hint. */
export function ImageUploadControl({
  hasImage,
  inputLabel,
  onUpload,
  onRemove,
  onSuccess,
  onError,
  disabled = false,
  className = '',
}: ImageUploadControlProps) {
  const { t } = useTranslation('common');
  const inputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);

  async function run(action: () => Promise<void>, successKey: string, failureKey: string) {
    setBusy(true);
    try {
      await action();
      onSuccess(t(successKey));
    } catch (err) {
      console.error(err);
      onError(t(ERROR_KEYS[errorCode(err) ?? ''] ?? failureKey));
    } finally {
      setBusy(false);
    }
  }

  function handleSelected(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = ''; // choosing the same file again must fire onChange
    if (!file) return;
    if (!IMAGE_ACCEPTED_TYPES.includes(file.type)) {
      onError(t('imageUpload.invalidType'));
      return;
    }
    if (file.size > IMAGE_MAX_BYTES) {
      onError(t('imageUpload.tooLarge'));
      return;
    }
    void run(() => onUpload(file), 'imageUpload.uploadSuccess', 'imageUpload.uploadFailed');
  }

  return (
    <div className={`flex flex-col gap-1.5 ${className}`}>
      <div className="flex flex-wrap gap-2">
        <input
          ref={inputRef}
          type="file"
          accept={IMAGE_ACCEPTED_TYPES.join(',')}
          aria-label={inputLabel}
          className="sr-only"
          tabIndex={-1}
          disabled={disabled || busy}
          onChange={handleSelected}
        />
        <ButtonApp
          label={hasImage ? t('imageUpload.change') : t('imageUpload.upload')}
          variant="secondary"
          size="small"
          icon={<Camera className="h-3.5 w-3.5" aria-hidden="true" />}
          loading={busy}
          disabled={disabled || busy}
          onClick={() => inputRef.current?.click()}
        />
        {hasImage && (
          <ButtonApp
            label={t('imageUpload.remove')}
            variant="secondary"
            size="small"
            icon={<Trash2 className="h-3.5 w-3.5" aria-hidden="true" />}
            disabled={disabled || busy}
            onClick={() => void run(onRemove, 'imageUpload.removeSuccess', 'imageUpload.removeFailed')}
          />
        )}
      </div>
      <p className="text-xs text-fg-tertiary dark:text-fg-tertiary-dark">{t('imageUpload.hint')}</p>
    </div>
  );
}

export default ImageUploadControl;
