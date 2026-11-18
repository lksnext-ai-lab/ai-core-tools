import React, { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { configService } from '../core/ConfigService';
import CardApp from '../components/ui/CardApp';
import Alert from '../components/ui/Alert';
import ButtonLink from '../components/ui/ButtonLink';
import { LoadingState } from '../components/ui/LoadingState';

const VerifyEmailPage: React.FC = () => {
  const { t } = useTranslation('common');
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token');
  const [status, setStatus] = useState<'loading' | 'success' | 'error'>('loading');
  const [message, setMessage] = useState('');

  useEffect(() => {
    if (!token) {
      setStatus('error');
      setMessage(t('verifyEmailPage.missingToken'));
      return;
    }

    const verify = async () => {
      try {
        const baseUrl = configService.getApiBaseUrl();
        const response = await fetch(`${baseUrl}/internal/auth/verify-email`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ token }),
        });
        const data = await response.json();
        if (response.ok) {
          setStatus('success');
          setMessage(data.message || t('verifyEmailPage.successMessage'));
        } else {
          setStatus('error');
          setMessage(data.detail || t('verifyEmailPage.failureMessage'));
        }
      } catch {
        setStatus('error');
        setMessage(t('verifyEmailPage.unexpectedError'));
      }
    };

    void verify();
  }, [token, t]);

  return (
    <div className="flex items-center justify-center min-h-screen px-4 text-fg bg-gradient-to-b from-canvas-alt to-surface dark:text-fg-dark dark:from-canvas-alt-dark dark:to-surface-dark">
      <div className="max-w-md w-full">
        <CardApp className="p-8">
          {status === 'loading' && (
            <LoadingState variant="section" message={t('verifyEmailPage.verifying')} />
          )}
          {status === 'success' && (
            <div className="space-y-4">
              <Alert
                type="success"
                title={t('verifyEmailPage.successTitle')}
                message={message}
              />
              <ButtonLink
                label={t('setPasswordPage.backToSignIn')}
                to="/login"
                variant="secondary"
                size="medium"
                className="w-full"
              />
            </div>
          )}
          {status === 'error' && (
            <div className="space-y-4">
              <Alert
                type="error"
                title={t('verifyEmailPage.failureTitle')}
                message={message}
              />
              <ButtonLink
                label={t('setPasswordPage.backToSignIn')}
                to="/login"
                variant="secondary"
                size="medium"
                className="w-full"
              />
            </div>
          )}
        </CardApp>
      </div>
    </div>
  );
};

export default VerifyEmailPage;
