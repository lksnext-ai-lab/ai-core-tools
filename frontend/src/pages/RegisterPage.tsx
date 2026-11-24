import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { apiService } from '../services/api';
import CardApp from '../components/ui/CardApp';
import Alert from '../components/ui/Alert';
import ButtonApp from '../components/ui/ButtonApp';
import ButtonLink from '../components/ui/ButtonLink';
import { FormField } from '../components/ui/FormField';

const RegisterPage = () => {
  const { t } = useTranslation('common');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsLoading(true);
    try {
      await apiService.register(email, password);
      setSuccess(true);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : t('registerPage.registrationFailed'));
    } finally {
      setIsLoading(false);
    }
  };

  const pageBackground = 'flex min-h-screen items-center justify-center px-4 text-fg bg-gradient-to-b from-canvas-alt to-surface dark:text-fg-dark dark:from-canvas-alt-dark dark:to-surface-dark';

  if (success) {
    return (
      <div className={pageBackground}>
        <div className="w-full max-w-md">
          <Alert
            type="success"
            title={t('registerPage.successTitle')}
            message={t('registerPage.successMessage', { email })}
          />
        </div>
      </div>
    );
  }

  return (
    <div className={pageBackground}>
      <CardApp className="p-8" titulo={t('registerPage.title')}>
        {error && <Alert type="error" message={error} className="mb-4" />}
        <form onSubmit={handleSubmit} className="space-y-4">
          <FormField
            id="register-email"
            label={t('login.emailLabel')}
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            autoComplete="email"
          />
          <FormField
            id="register-password"
            label={t('login.passwordLabel')}
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={8}
            autoComplete="new-password"
          />
          <ButtonApp
            label={isLoading ? t('registerPage.creatingAccount') : t('registerPage.submit')}
            type="submit"
            disabled={isLoading}
            loading={isLoading}
            variant="primary"
            size="medium"
            className="w-full"
          />
        </form>
        <ButtonLink
          label={t('registerPage.signIn')}
          to="/login"
          variant="secondary"
          size="medium"
          className="mt-4 w-full"
        />
        <p className="mt-6 border-t border-line pt-4 text-center text-sm text-fg-tertiary dark:border-line-dark dark:text-fg-tertiary-dark">
          {t('registerPage.socialLoginComingSoon')}
        </p>
      </CardApp>
    </div>
  );
};

export default RegisterPage;
