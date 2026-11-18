import { useState, useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { authService } from '../services/auth';
import { useUser } from '../contexts/UserContext';
import Alert from '../components/ui/Alert';
import { ButtonApp } from '../components/ui/ButtonApp';
import ButtonLink from '../components/ui/ButtonLink';
import CardApp from '../components/ui/CardApp';
import { FormField } from '../components/ui/FormField';

export interface ChangePasswordPageProps {
  readonly className?: string;
}

const MIN_PASSWORD_LENGTH = 12;

function ChangePasswordPage() {
  const navigate = useNavigate();
  const { t } = useTranslation('common');
  const { user } = useUser();

  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const successHeadingRef = useRef<HTMLHeadingElement>(null);

  // Move focus to the success heading so screen readers announce the state change.
  useEffect(() => {
    if (success && successHeadingRef.current) {
      successHeadingRef.current.focus();
    }
  }, [success]);

  const validationError = (): string | null => {
    if (newPassword.length < MIN_PASSWORD_LENGTH) {
      return t('changePasswordPage.passwordTooShort', { count: MIN_PASSWORD_LENGTH });
    }
    if (newPassword !== confirm) {
      return t('changePasswordPage.passwordsDoNotMatch');
    }
    if (newPassword === currentPassword) {
      return t('changePasswordPage.passwordMustBeDifferent');
    }
    return null;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    const ve = validationError();
    if (ve) {
      setError(ve);
      return;
    }

    setIsLoading(true);
    try {
      await authService.changePassword(currentPassword, newPassword);
      setSuccess(true);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : t('changePasswordPage.changeFailed'));
    } finally {
      setIsLoading(false);
    }
  };

  if (success) {
    return (
      <div className="flex flex-1 items-center justify-center px-4">
        <main className="w-full max-w-md">
          <CardApp variant="white" className="p-8 text-center">
            <div role="status" aria-live="polite">
              <div className="w-12 h-12 rounded-full bg-success-bg dark:bg-success-bg-dark flex items-center justify-center mx-auto mb-4" aria-hidden="true">
                <svg className="w-6 h-6 text-success dark:text-success-dark" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} aria-hidden="true">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
                </svg>
              </div>
              <h1
                ref={successHeadingRef}
                tabIndex={-1}
                className="text-xl font-bold text-fg dark:text-fg-dark mb-2 focus:outline-none"
              >
                {t('changePasswordPage.successTitle')}
              </h1>
              <p className="text-sm text-fg-secondary dark:text-fg-secondary-dark mb-6">
                {t('changePasswordPage.successMessage')}
              </p>
            </div>
            <ButtonApp
              label={t('changePasswordPage.goToSignIn')}
              onClick={() => authService.logout().finally(() => navigate('/login', { replace: true }))}
              size="spacious"
              className="w-full"
            />
          </CardApp>
        </main>
      </div>
    );
  }

  return (
    <div className="flex flex-1 items-center justify-center px-4">
      <main className="max-w-md w-full">
        <CardApp
          variant="white"
          className="p-8 [&>div>div>h4]:text-xl"
          titulo={t('changePasswordPage.title')}
          subtitulo={t('changePasswordPage.description')}
        >
        
        {/* Always-rendered so screen readers receive the alert before the error fires */}
        <div id="change-password-error" className={error ? 'mb-4' : 'sr-only'}>
          <Alert type="error" message={error ?? ''} />
        </div>

        <form onSubmit={handleSubmit} className="space-y-5" noValidate>
          {/* Hidden username field — helps password managers associate the new password with this account */}
          {user?.email && (
            <FormField
              id="change-password-username"
              type="email"
              value={user.email}
              autoComplete="username"
              ariaHidden
              tabIndex={-1}
              readOnly
              className="sr-only"
            />
          )}

          <FormField
            id="current-password"
            label={t('changePasswordPage.currentPassword')}
            type="password"
            value={currentPassword}
            onChange={(e) => setCurrentPassword(e.target.value)}
            required
            ariaRequired
            ariaInvalid={error !== null}
            ariaDescribedBy="change-password-error"
            autoComplete="current-password"
            disabled={isLoading}
          />

          <FormField
            id="new-password"
            label={t('changePasswordPage.newPassword')}
            type="password"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            required
            ariaRequired
            ariaInvalid={error !== null}
            ariaDescribedBy="change-password-error"
            autoComplete="new-password"
            helpText={t('changePasswordPage.passwordMinLength', { count: MIN_PASSWORD_LENGTH })}
            disabled={isLoading}
          />

          <FormField
            id="confirm-password"
            label={t('changePasswordPage.confirmNewPassword')}
            type="password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            required
            ariaRequired
            ariaInvalid={error !== null}
            ariaDescribedBy="change-password-error"
            autoComplete="new-password"
            disabled={isLoading}
          />

          <ButtonApp
            type="submit"
            label={isLoading ? t('changePasswordPage.changing') : t('changePasswordPage.submit')}
            disabled={!currentPassword || !newPassword || !confirm}
            loading={isLoading}
            size="spacious"
            className="w-full"
          />
          <ButtonLink
            to="/apps"
            label={t('changePasswordPage.cancel')}
            variant="secondary"
            size="spacious"
            className="w-full"
          />
        </form>
        </CardApp>
      </main>
    </div>
  );
}

export default ChangePasswordPage;
