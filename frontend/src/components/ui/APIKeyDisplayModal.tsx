import { useState } from 'react';
import Modal from './Modal';
import Alert from './Alert';
import { ButtonApp } from './ButtonApp';
import CardApp from './CardApp';

interface APIKeyDisplayModalProps {
  isOpen: boolean;
  onClose: () => void;
  apiKey: {
    name: string;
    key_value: string;
    message: string;
  } | null;
}

function APIKeyDisplayModal({ isOpen, onClose, apiKey }: Readonly<APIKeyDisplayModalProps>) {
  const [copied, setCopied] = useState(false);

  const copyToClipboard = async () => {
    if (!apiKey?.key_value) return;

    try {
      await navigator.clipboard.writeText(apiKey.key_value);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error('Failed to copy to clipboard:', err);
    }
  };

  const handleClose = () => {
    setCopied(false);
    onClose();
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={handleClose}
      title="API Key Created Successfully"
    >
      <div className="space-y-6">
        {/* Success Message */}
        <Alert type="success" title="API Key Created" message={apiKey?.message} />

        {/* API Key Details */}
        <div>
          <p className="block text-sm font-medium text-fg dark:text-fg-dark mb-2">
            API Key Name
          </p>
          <CardApp className="px-3 py-2">
            {apiKey?.name}
          </CardApp>
        </div>

        {/* API Key Value */}
        <div>
          <label htmlFor="api-key-value" className="block text-sm font-medium text-fg dark:text-fg-dark mb-2">
            API Key
          </label>
          <div className="relative">
            <textarea
              id="api-key-value"
              readOnly
              value={apiKey?.key_value || ''}
              className="w-full px-3 py-2 text-sm border rounded-lg bg-surface text-fg placeholder:text-fg-faint dark:bg-surface-dark dark:text-fg-dark dark:placeholder:text-fg-faint-dark focus:outline-none focus:border-accent dark:border-line-strong-dark dark:focus:border-accent font-mono resize-none"
              rows={3}
            />
            <ButtonApp
              label={copied ? 'Copied!' : 'Copy'}
              variant="primary"
              size="medium"
              onClick={copyToClipboard}
              className="absolute top-2 right-2"
            />
          </div>
        </div>

        {/* Security Warning */}
        <Alert
          type="warning"
          title="Important Security Notice"
          message={(
            <ul className="list-disc list-inside space-y-1">
              <li>This is the only time you will see this API key</li>
              <li>Copy and store it in a secure location immediately</li>
              <li>Never share this key publicly or commit it to version control</li>
              <li>If you lose this key, you'll need to create a new one</li>
            </ul>
          )}
        />

        {/* Close Button */}
        <div className="flex justify-end pt-4 border-t border-gray-200">
          <ButtonApp
            label="I've Saved the Key"
            variant="primary"
            size="medium"
            onClick={handleClose}
          />
        </div>
      </div>
    </Modal>
  );
}

export default APIKeyDisplayModal;
