import { useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useUser } from '../contexts/UserContext';
import { oidcService } from '../services/oidc';

function LoginPage() {
  const [loadingProvider, setLoadingProvider] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();
  const location = useLocation();
  const { user, loading } = useUser();
  const providers = oidcService.getAvailableProviders();

  const from = location.state?.from?.pathname || '/apps';

  useEffect(() => {
    if (!loading && user) {
      navigate(from, { replace: true });
    }
  }, [user, loading, navigate, from]);

  const handleLogin = async (providerKey: string) => {
    try {
      setError(null);
      setLoadingProvider(providerKey);
      await oidcService.startLogin(providerKey);
    } catch (err) {
      setLoadingProvider(null);
      setError(err instanceof Error ? err.message : 'Unable to start login flow');
    }
  };

  if (!loading && user) {
    return null;
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-blue-50 to-indigo-100">
      <div className="max-w-md w-full space-y-8 p-8">
        <div className="text-center">
          <div className="mx-auto h-16 w-16 bg-gradient-to-br from-blue-500 to-indigo-600 rounded-2xl flex items-center justify-center mb-4">
            <span className="text-white text-2xl font-bold">🤖</span>
          </div>
          <h2 className="text-3xl font-bold text-gray-900">Welcome to Mattin AI</h2>
          <p className="mt-2 text-gray-600">Sign in to access your AI workspace</p>
        </div>

        <div className="bg-white rounded-xl shadow-lg p-8 space-y-6">
          {error && (
            <div className="bg-red-50 border border-red-200 rounded-lg p-4">
              <div className="flex items-center">
                <span className="text-red-400 text-xl mr-3">⚠️</span>
                <div>
                  <h3 className="text-sm font-medium text-red-800">Login Error</h3>
                  <p className="text-sm text-red-600 mt-1">{error}</p>
                </div>
              </div>
            </div>
          )}

          {providers.length === 0 ? (
            <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4 text-sm text-yellow-800">
              <p className="font-medium">No identity providers configured.</p>
              <p className="mt-1">Please configure OIDC providers in your environment variables.</p>
            </div>
          ) : (
            <div className="space-y-3">
              {providers.map((provider) => (
                <button
                  key={provider.key}
                  onClick={() => handleLogin(provider.key)}
                  disabled={!!loadingProvider}
                  className="w-full flex items-center justify-center px-4 py-3 border border-gray-300 rounded-lg shadow-sm bg-white text-gray-700 hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  {loadingProvider === provider.key ? (
                    <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-indigo-600 mr-3"></div>
                  ) : (
                    <span className="mr-3 text-lg">🔐</span>
                  )}
                  {loadingProvider === provider.key ? `Redirecting to ${provider.name}...` : `Continue with ${provider.name}`}
                </button>
              ))}
            </div>
          )}

          <div className="pt-4 border-t border-gray-200">
            <h3 className="text-sm font-medium text-gray-900 mb-3">What you'll get:</h3>
            <ul className="space-y-2 text-sm text-gray-600">
              <li className="flex items-center">
                <span className="text-green-500 mr-2">✓</span>
                Create and manage AI agents
              </li>
              <li className="flex items-center">
                <span className="text-green-500 mr-2">✓</span>
                Process documents and data
              </li>
              <li className="flex items-center">
                <span className="text-green-500 mr-2">✓</span>
                Collaborate with your team
              </li>
              <li className="flex items-center">
                <span className="text-green-500 mr-2">✓</span>
                Access powerful AI tools
              </li>
            </ul>
          </div>
        </div>

        <div className="text-center text-sm text-gray-500">
          <p>
            By signing in, you agree to our{' '}
            <a href="#" className="text-indigo-600 hover:text-indigo-500">Terms of Service</a>
            {' '}and{' '}
            <a href="#" className="text-indigo-600 hover:text-indigo-500">Privacy Policy</a>
          </p>
        </div>
      </div>
    </div>
  );
}

export default LoginPage;
