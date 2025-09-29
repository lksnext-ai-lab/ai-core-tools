import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { oidcService } from '../services/oidc';

function AuthSuccessPage() {
  const [status, setStatus] = useState<'processing' | 'error'>('processing');
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    const completeLogin = async () => {
      try {
        await oidcService.handleAuthCallback();
        navigate('/apps', { replace: true });
      } catch (err) {
        console.error('OIDC callback error:', err);
        setStatus('error');
        setError(err instanceof Error ? err.message : 'Authentication failed.');
      }
    };

    void completeLogin();
  }, [navigate]);

  if (status === 'processing') {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-blue-50 to-indigo-100">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600 mx-auto mb-4"></div>
          <h2 className="text-xl font-semibold text-gray-900">Completing sign in...</h2>
          <p className="text-gray-600 mt-2">Please wait while we validate your credentials.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-red-50 to-rose-100">
      <div className="max-w-md w-full space-y-8 p-8">
        <div className="text-center">
          <div className="mx-auto h-16 w-16 bg-red-500 rounded-full flex items-center justify-center mb-4">
            <span className="text-white text-2xl">✗</span>
          </div>
          <h2 className="text-xl font-semibold text-gray-900">Sign in failed</h2>
          <p className="text-gray-600 mt-2">{error}</p>
        </div>

        <div className="text-center">
          <button
            onClick={() => navigate('/login')}
            className="px-6 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg transition-colors"
          >
            Try Again
          </button>
        </div>
      </div>
    </div>
  );
}

export default AuthSuccessPage;
