import { useState, useEffect, useRef } from 'react';
import { Copy, Check } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import Modal from './Modal';
import Alert from './Alert';
import FormField from './FormField';
import { ButtonApp } from './ButtonApp';

export interface OneTimeLinkModalProps {
  readonly isOpen: boolean;
  readonly onClose: () => void;
  readonly token: string;
  readonly expiresAt: string;
  /**
   * Optional heading shown at the top of the success state.
   * Defaults to "Set-Password Link Ready".
   */
  readonly title?: string;
}

function buildSetPasswordLink(token: string): string {
  return `${window.location.origin}/set-password?token=${encodeURIComponent(token)}`;
}

function formatExpiry(isoString: string, language: string): string {
  try {
    return new Date(isoString).toLocaleString(language, {
      dateStyle: 'medium',
      timeStyle: 'short',
    });
  } catch {
    return isoString;
  }
}

function OneTimeLinkModal({ isOpen, onClose, token, expiresAt, title }: OneTimeLinkModalProps) {
  const { t, i18n } = useTranslation('common');
  const [copied, setCopied] = useState(false);
  const [copyFailed, setCopyFailed] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const link = buildSetPasswordLink(token);

  // Move focus to the copyable input on open so screen-reader users land on the value immediately.
  useEffect(() => {
    if (isOpen && inputRef.current) {
      inputRef.current.focus();
    }
  }, [isOpen]);

  async function handleCopy() {
    setCopyFailed(false);
    try {
      await navigator.clipboard.writeText(link);
      setCopied(true);
      setTimeout(() => setCopied(false), 2500);
    } catch {
      // Clipboard unavailable (permission denied or insecure context) — select text for manual copy.
      inputRef.current?.select();
      setCopied(false);
      setCopyFailed(true);
    }
  }

  function handleClose() {
    setCopied(false);
    setCopyFailed(false);
    onClose();
  }

  return (
    <Modal isOpen={isOpen} onClose={handleClose} title={title ?? t('oneTimeLink.title')} size="large">
      <div className="space-y-5">
        <Alert
          type="success"
          message={t('oneTimeLink.generatedMessage')}
        />

        <div>
          <label htmlFor="onetimelink-value" className="block text-sm font-medium text-gray-700 dark:text-slate-300 mb-1.5">
            {t('oneTimeLink.label')}
          </label>
          <div className="flex gap-2">
            <FormField
              ref={inputRef}
              id="onetimelink-value"
              type="text"
              readOnly
              value={link}
              className="flex-1 min-w-0"
              inputClassName="flex-1 min-w-0 "
              onFocus={(e) => e.currentTarget.select()}
            />
            <ButtonApp
              label={copied ? t('oneTimeLink.copied') : t('oneTimeLink.copy')}
              onClick={handleCopy}
              ariaLabel={copied ? t('oneTimeLink.linkCopied') : t('oneTimeLink.copyLink')}
              variant="primary"
              size="medium"
              icon={copied
                ? <Check className="w-4 h-4" aria-hidden="true" />
                : <Copy className="w-4 h-4" aria-hidden="true" />}
              className="flex-shrink-0"
            />
          </div>
          {/* Always-rendered so copy status is reliably announced to AT */}
          <p
            role="status"
            aria-live="polite"
            className={`mt-1.5 text-xs ${copyFailed ? 'text-amber-700 dark:text-amber-400' : 'text-green-700 dark:text-green-400'}`}
          >
            {copied && t('oneTimeLink.linkCopied')}
            {copyFailed && t('oneTimeLink.copyUnavailable')}
          </p>
        </div>

        <Alert
          type="warning"
          title={t('oneTimeLink.shownOnce')}
          message={(
            <ul className="list-disc list-inside space-y-0.5">
              <li>{t('oneTimeLink.expiresOn')} <strong>{formatExpiry(expiresAt, i18n.language)}</strong>.</li>
              <li>{t('oneTimeLink.sendSecurely')}</li>
              <li>{t('oneTimeLink.singleUse')}</li>
            </ul>
          )}
        />

        <div className="flex justify-end border-t border-line dark:border-line-dark pt-4">
          <ButtonApp
            label={t('formActions.cancel')}
            onClick={handleClose}
            variant="secondary"
            size="medium"
          />
        </div>
      </div>
    </Modal>
  );
}

export default OneTimeLinkModal;
