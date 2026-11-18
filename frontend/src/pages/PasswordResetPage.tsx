import React, { useState } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { configService } from '../core/ConfigService';
import CardApp from '../components/ui/CardApp';
import Alert from '../components/ui/Alert';
import ButtonApp from '../components/ui/ButtonApp';
import { FormField } from '../components/ui/FormField';

const PasswordResetPage: React.FC = () => {
  const { t } = useTranslation('common');
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token') ?? '';
  const [newPassword, setNewPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsLoading(true);
    try {
      const baseUrl = configService.getApiBaseUrl();
      const response = await fetch(`${baseUrl}/internal/auth/password-reset`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token, new_password: newPassword }),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || t('passwordResetPage.resetFailed'));
      }
      setSuccess(true);
      setTimeout(() => navigate('/login'), 2000);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('passwordResetPage.resetFailed'));
    } finally {
      setIsLoading(false);
    }
  };

  if (success) {
    return (
      <div className="flex items-center justify-center min-h-screen px-4 text-fg bg-gradient-to-b from-canvas-alt to-surface dark:text-fg-dark dark:from-canvas-alt-dark dark:to-surface-dark">
        <div className="max-w-md w-full">
          <Alert
            type="success"
            title={t('passwordResetPage.successTitle')}
            message={t('passwordResetPage.redirectingToLogin')}
          />
        </div>
      </div>
    );
  }

  return (
    <div className="flex items-center justify-center min-h-screen px-4 text-fg bg-gradient-to-b from-canvas-alt to-surface dark:text-fg-dark dark:from-canvas-alt-dark dark:to-surface-dark">
      <CardApp className="p-8" titulo={t('passwordResetPage.setNewPassword')}>
        {error && <Alert type="error" message={error} className="mb-4" />}
        <form onSubmit={handleSubmit} className="space-y-4">
          <FormField
            id="new-password"
            label={t('setPasswordPage.newPassword')}
            type="password"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            required
            minLength={8}
          />
          <ButtonApp
            label={isLoading ? t('formActions.saving') : t('passwordResetPage.setNewPassword')}
            type="submit"
            disabled={!token}
            loading={isLoading}
            variant="primary"
            size="medium"
            className="w-full"
          />
        </form>
      </CardApp>
    </div>
  );
};

export default PasswordResetPage;
