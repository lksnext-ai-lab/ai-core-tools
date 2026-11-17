import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { configService } from '../core/ConfigService';
import CardApp from '../components/ui/CardApp';
import Alert from '../components/ui/Alert';
import ButtonApp from '../components/ui/ButtonApp';
import ButtonLink from '../components/ui/ButtonLink';
import { FormField } from '../components/ui/FormField';

const PasswordResetRequestPage: React.FC = () => {
  const { t } = useTranslation('common');
  const [email, setEmail] = useState('');
  const [submitted, setSubmitted] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    try {
      const baseUrl = configService.getApiBaseUrl();
      await fetch(`${baseUrl}/internal/auth/password-reset-request`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email }),
      });
    } finally {
      setIsLoading(false);
      setSubmitted(true); // Always show success to prevent enumeration
    }
  };

  if (submitted) {
    return (
      <div className="flex items-center justify-center min-h-screen px-4 text-fg bg-gradient-to-b from-canvas-alt to-surface dark:text-fg-dark dark:from-canvas-alt-dark dark:to-surface-dark">
        <div className="max-w-md w-full space-y-4">
          <Alert
            type="success"
            title={t('passwordResetRequestPage.successTitle')}
            message={t('passwordResetRequestPage.successMessage')}
          />
          <Link to="/login" className="block text-center text-sm text-bronze dark:text-bronze-dark hover:underline">
            {t('setPasswordPage.backToSignIn')}
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="flex items-center justify-center min-h-screen px-4 text-fg bg-gradient-to-b from-canvas-alt to-surface dark:text-fg-dark dark:from-canvas-alt-dark dark:to-surface-dark">
      <CardApp className="p-8" titulo={t('passwordResetRequestPage.title')}>
        <form onSubmit={handleSubmit} className="space-y-4">
          <FormField
            id="email"
            label={t('login.emailLabel')}
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            autoComplete="email"
          />
          <ButtonApp
            label={isLoading
              ? t('passwordResetRequestPage.sending')
              : t('passwordResetRequestPage.submit')}
            type="submit"
            disabled={isLoading}
            loading={isLoading}
            variant="primary"
            size="medium"
            className="w-full"
          />
        </form>
        <ButtonLink
          label={t('setPasswordPage.backToSignIn')}
          to="/login"
          variant="secondary"
          size="medium"
          className="mt-4 w-full"
        />
      </CardApp>
    </div>
  );
};

export default PasswordResetRequestPage;
