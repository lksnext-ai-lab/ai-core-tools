import { useState, useRef, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import Modal from './Modal';
import OneTimeLinkModal from './OneTimeLinkModal';
import { adminService } from '../../services/admin';
import type { LocalUserCreated } from '../../services/admin';
import { ApiError } from '../../services/api';
import { errorMessage } from '../../constants/messages';
import { FormActions } from './FormActions';
import FormField from './FormField';

export interface CreateLocalUserModalProps {
  readonly isOpen: boolean;
  readonly onClose: () => void;
  /** Called after a user is successfully created so the parent can refresh the list. */
  readonly onCreated: () => void;
}

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function CreateLocalUserModal({ isOpen, onClose, onCreated }: CreateLocalUserModalProps) {
  const { t } = useTranslation('common');
  const [email, setEmail] = useState('');
  const [name, setName] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  // Track 409 duplicate-email separately so the field can be marked invalid despite passing format validation.
  const [emailTaken, setEmailTaken] = useState(false);
  const [createdUser, setCreatedUser] = useState<LocalUserCreated | null>(null);
  const [showLink, setShowLink] = useState(false);

  const emailInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (isOpen && !showLink) {
      // Defer one tick so Modal has finished rendering before focusing.
      const id = setTimeout(() => emailInputRef.current?.focus(), 50);
      return () => clearTimeout(id);
    }
  }, [isOpen, showLink]);

  useEffect(() => {
    if (!isOpen) {
      setEmail('');
      setName('');
      setFormError(null);
      setIsSubmitting(false);
      setCreatedUser(null);
      setShowLink(false);
    }
  }, [isOpen]);

  function validate(): string | null {
    if (!email.trim()) return t('localUserModal.emailRequired');
    if (!EMAIL_PATTERN.test(email.trim())) return t('localUserModal.emailInvalid');
    if (!name.trim()) return t('localUserModal.nameRequired');
    return null;
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setFormError(null);

    const ve = validate();
    if (ve) {
      setFormError(ve);
      return;
    }

    setIsSubmitting(true);
    setEmailTaken(false);
    try {
      const result = await adminService.createLocalUser(email.trim(), name.trim());
      setCreatedUser(result);
      setShowLink(true);
    } catch (err: unknown) {
      if (err instanceof ApiError && err.status === 409) {
        setEmailTaken(true);
        setFormError(t('localUserModal.emailExists'));
      } else {
        setFormError(errorMessage(err, t('localUserModal.createFailed')));
      }
    } finally {
      setIsSubmitting(false);
    }
  }

  function handleLinkClose() {
    setShowLink(false);
    onCreated();
    onClose();
  }

  if (showLink && createdUser) {
    return (
      <OneTimeLinkModal
        isOpen={true}
        onClose={handleLinkClose}
        token={createdUser.set_password_token}
        expiresAt={createdUser.expires_at}
        title={t('localUserModal.createdTitle', { email: createdUser.email })}
      />
    );
  }

  return (
    <Modal isOpen={isOpen} onClose={onClose} title={t('userManagement.createUser')} size="medium">
      <form onSubmit={handleSubmit} noValidate className="space-y-5">
        <p className="text-xs text-gray-500 dark:text-slate-400">{t('localUserModal.requiredFields')}</p>
        {/* Always in DOM — role=alert implies aria-live=assertive */}
        <div
          id="create-user-error"
          role="alert"
          className={formError
            ? 'flex items-start gap-3 rounded-lg px-4 py-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800'
            : 'sr-only'}
        >
          {formError && (
            <p className="text-sm text-red-700 dark:text-red-300">{formError}</p>
          )}
        </div>

        <FormField
          ref={emailInputRef}
          label={t('localUserModal.email')}
          labelClassName="block text-sm font-medium text-gray-700 dark:text-slate-300 mb-1.5"
          id="create-user-email"
          type="email"
          value={email}
          onChange={(e) => { setEmail(e.target.value); setEmailTaken(false); }}
          required
          ariaRequired
          ariaInvalid={emailTaken || (formError !== null && (!email.trim() || !EMAIL_PATTERN.test(email.trim())))}
          ariaDescribedBy="create-user-error"
          autoComplete="email"
          disabled={isSubmitting}
          placeholder={t('login.emailPlaceholder')}
        />

        <FormField
          label={t('localUserModal.fullName')}
          labelClassName="block text-sm font-medium text-gray-700 dark:text-slate-300 mb-1.5"
          id="create-user-name"
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
          ariaRequired
          ariaInvalid={formError !== null && !name.trim()}
          ariaDescribedBy="create-user-error"
          autoComplete="name"
          disabled={isSubmitting}
          placeholder={t('localUserModal.namePlaceholder')}
        />

        <FormActions
          onCancel={onClose}
          isSubmitting={isSubmitting}
          submitLabel={t('userManagement.createUser')}
          submittingLabel={t('localUserModal.creating')}
        />
      </form>
    </Modal>
  );
}

export default CreateLocalUserModal;
