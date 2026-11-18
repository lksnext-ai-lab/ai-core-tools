import { useContext, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import { OIDCContext } from '../auth/OIDCProvider';
import Alert from '../components/ui/Alert';
import ButtonApp from '../components/ui/ButtonApp';
import { LoadingState } from '../components/ui/LoadingState';
import CardApp from '../components/ui/CardApp';

function AuthSuccessPage() {
  const [error, setError] = useState<string | null>(null);
  const { t } = useTranslation('common');
  const navigate = useNavigate();
  const { isAuthenticated, loading, sessionError } = useAuth();
  const returnTo = useContext(OIDCContext)?.returnTo ?? null;

  useEffect(() => {
    if (loading) return;
    if (isAuthenticated) {
      navigate(returnTo ?? '/', { replace: true });
    } else if (sessionError === 'unavailable') {
      setError(t('authSuccessPage.serverUnavailable'));
    } else {
      setError(t('authSuccessPage.authenticationFailed'));
    }
  }, [isAuthenticated, loading, sessionError, returnTo, navigate, t]);

  if (loading) {
    return (
      <CardApp className="min-h-screen flex items-center justify-center ">
        <div className="text-center">
          <LoadingState variant="indicator" className="mb-4" />
          <h2 className="text-xl font-semibold text-fg dark:text-fg-dark">{t('authSuccessPage.completingSignIn')}</h2>
          <p className="text-fg-secondary  dark:text-fg-secondary-dark mt-2">{t('authSuccessPage.settingUpAccount')}</p>
        </div>
      </CardApp>
    );
  }

  if (error) {
    return (
      <div>
        <div className="max-w-md w-full space-y-8 p-8">
          <Alert type="error" title={t('authSuccessPage.signInFailed')} message={error} />
          
          <div className="text-center">
            <ButtonApp
              label={t('authSuccessPage.tryAgain')}
              onClick={() => navigate('/login', { replace: true })}
              variant="primary"
              size="medium"
            />
          </div>
        </div>
      </div>
    );
  }

  // Loading is complete and authenticated, will redirect via useEffect
  return null;
}

export default AuthSuccessPage; 