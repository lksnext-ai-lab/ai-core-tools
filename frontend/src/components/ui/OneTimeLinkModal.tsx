import { useState, useEffect, useRef } from 'react';
import { CheckCircle2, AlertTriangle, Copy, Check } from 'lucide-react';
import Modal from './Modal';

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
    <Modal isOpen={isOpen} onClose={handleClose} title={title} size="medium">
      <div className="space-y-5">
        <div className="flex items-start gap-3 rounded-lg bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 p-4">
          <CheckCircle2 className="w-5 h-5 text-green-500 dark:text-green-400 flex-shrink-0 mt-0.5" aria-hidden="true" />
          <p className="text-sm text-green-800 dark:text-green-300">
            The one-time link has been generated. Copy it now and send it to the user
            over a secure channel (e.g. direct message or encrypted email). The link
            will not be shown again.
          </p>
        </div>

        <div>
          <label htmlFor="onetimelink-value" className="block text-sm font-medium text-gray-700 dark:text-slate-300 mb-1.5">
            Set-password link
          </label>
          <div className="flex gap-2">
            <input
              ref={inputRef}
              id="onetimelink-value"
              type="text"
              readOnly
              value={link}
              className="flex-1 min-w-0 px-3 py-2 bg-gray-50 dark:bg-slate-700 border border-gray-300 dark:border-slate-600 rounded-lg text-sm font-mono text-gray-800 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
              onFocus={(e) => e.currentTarget.select()}
            />
            <button
              type="button"
              onClick={handleCopy}
              aria-label={copied ? 'Link copied to clipboard' : 'Copy link to clipboard'}
              className="flex-shrink-0 inline-flex items-center gap-1.5 px-3 py-2 bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 text-white text-sm rounded-lg transition-colors"
            >
              {copied ? (
                <>
                  <Check className="w-4 h-4" aria-hidden="true" />
                  Copied
                </>
              ) : (
                <>
                  <Copy className="w-4 h-4" aria-hidden="true" />
                  Copy
                </>
              )}
            </button>
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

        <div className="flex items-start gap-3 rounded-lg bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 p-4">
          <AlertTriangle className="w-5 h-5 text-amber-500 dark:text-amber-400 flex-shrink-0 mt-0.5" aria-hidden="true" />
          <div className="space-y-1 text-sm text-amber-800 dark:text-amber-300">
            <p className="font-medium">This link is shown only once.</p>
            <ul className="list-disc list-inside space-y-0.5 text-amber-700 dark:text-amber-400">
              <li>It expires on <strong>{formatExpiry(expiresAt)}</strong>.</li>
              <li>Send it to the user over a secure, private channel.</li>
              <li>It can only be used once to set a password.</li>
            </ul>
          </div>
        </div>

        <div className="flex justify-end border-t border-gray-200 dark:border-slate-700 pt-4">
          <button
            type="button"
            onClick={handleClose}
            className="px-5 py-2 bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 text-white text-sm font-medium rounded-lg transition-colors"
          >
            Done
          </button>
        </div>
      </div>
    </Modal>
  );
}

export default OneTimeLinkModal;
