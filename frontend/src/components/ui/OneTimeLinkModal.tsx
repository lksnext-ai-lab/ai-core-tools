import { useState, useEffect, useRef } from 'react';
import { Copy, Check } from 'lucide-react';
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

function formatExpiry(isoString: string): string {
  try {
    return new Date(isoString).toLocaleString(undefined, {
      dateStyle: 'medium',
      timeStyle: 'short',
    });
  } catch {
    return isoString;
  }
}

function OneTimeLinkModal({ isOpen, onClose, token, expiresAt, title = 'Set-Password Link Ready' }: OneTimeLinkModalProps) {
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
    <Modal isOpen={isOpen} onClose={handleClose} title={title} size="large">
      <div className="space-y-5">
        <Alert
          type="success"
          message="The one-time link has been generated. Copy it now and send it to the user over a secure channel (e.g. direct message or encrypted email). The link will not be shown again."
        />

        <div>
          <label htmlFor="onetimelink-value" className="block text-sm font-medium text-gray-700 dark:text-slate-300 mb-1.5">
            Set-password link
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
              label={copied ? 'Copied' : 'Copy'}
              onClick={handleCopy}
              ariaLabel={copied ? 'Link copied to clipboard' : 'Copy link to clipboard'}
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
            {copied && 'Link copied to clipboard.'}
            {copyFailed && 'Auto-copy unavailable — select the link above and copy it manually.'}
          </p>
        </div>

        <Alert
          type="warning"
          title="This link is shown only once."
          message={(
            <ul className="list-disc list-inside space-y-0.5">
              <li>It expires on <strong>{formatExpiry(expiresAt)}</strong>.</li>
              <li>Send it to the user over a secure, private channel.</li>
              <li>It can only be used once to set a password.</li>
            </ul>
          )}
        />

        <div className="flex justify-end border-t border-gray-200 dark:border-slate-700 pt-4">
          <ButtonApp
            label="Done"
            onClick={handleClose}
            variant="primary"
            size="medium"
          />
        </div>
      </div>
    </Modal>
  );
}

export default OneTimeLinkModal;
