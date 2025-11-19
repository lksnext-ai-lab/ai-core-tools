import { useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { authService } from '../services/auth';
import { useUser } from '../contexts/UserContext';
import { useAuth } from '../auth/AuthContext';

function LoginPage() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [email, setEmail] = useState('');
  const navigate = useNavigate();
  const location = useLocation();
  const { user, refreshUser } = useUser();
  const auth = useAuth();

  // Determine if OIDC is enabled based on config
  // Try runtime config first, then fall back to build-time env var
  const runtimeConfig = (window as any).__RUNTIME_CONFIG__;
  const oidcEnabled = runtimeConfig?.VITE_OIDC_ENABLED === 'true' || 
                      import.meta.env.VITE_OIDC_ENABLED === 'true';

  // Get the intended destination or default to /apps
  const from = location.state?.from?.pathname || '/apps';

  // Check if already authenticated
  useEffect(() => {
    if (user || auth.isAuthenticated) {
      navigate(from, { replace: true });
    }
  }, [user, auth.isAuthenticated, navigate, from]);

  const handleOIDCLogin = async () => {
    try {
      setLoading(true);
      setError(null);
      await auth.login();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed');
      setLoading(false);
    }
  };

  const handleFakeLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!email?.includes('@')) {
      setError('Please enter a valid email address');
      return;
    }

    try {
      setLoading(true);
      setError(null);
      
      await authService.fakeLogin(email);
      
      // Refresh user context to trigger authentication check
      refreshUser();
      
      // Navigate to intended destination
      navigate(from, { replace: true });
    } catch (err: any) {
      const errorMessage = err?.message || 'Login failed';
      if (errorMessage.includes('not found')) {
        setError('User not found. Please contact an administrator.');
      } else {
        setError(errorMessage);
      }
      setLoading(false);
    }
  };

  // Don't show login page if user is already authenticated
  if (user || auth.isAuthenticated) {
    return null;
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-blue-50 to-indigo-100">
      <div className="max-w-md w-full space-y-8 p-8">
        {/* Logo and Title */}
        <div className="text-center">
          <div className="mx-auto h-16 w-16 bg-gradient-to-br from-blue-500 to-indigo-600 rounded-2xl flex items-center justify-center mb-4">
            <span className="text-white text-2xl font-bold">🤖</span>
          </div>
          <h2 className="text-3xl font-bold text-gray-900">Welcome to Mattin AI</h2>
          <p className="mt-2 text-gray-600">Sign in to access your AI workspace</p>
        </div>
        
        {/* Login Card */}
        <div className="bg-white rounded-xl shadow-lg p-8 space-y-6">
          {/* Development Mode Indicator */}
          {!oidcEnabled && (
            <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
              <div className="flex items-center">
                <span className="text-yellow-500 text-xl mr-3">⚠️</span>
                <div>
                  <h3 className="text-sm font-medium text-yellow-800">Development Mode</h3>
                  <p className="text-sm text-yellow-600 mt-1">Simple email login for testing</p>
                </div>
              </div>
            </div>
          )}

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

          {/* Fake Login Form */}
          {!oidcEnabled && (
            <form onSubmit={handleFakeLogin} className="space-y-4">
              <div>
                <label htmlFor="email" className="block text-sm font-medium text-gray-700 mb-2">
                  Email Address
                </label>
                <input
                  id="email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="user@example.com"
                  disabled={loading}
                  required
                  className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                />
              </div>
              <button
                type="submit"
                disabled={loading || !email}
                className="w-full flex items-center justify-center px-4 py-3 border border-transparent rounded-lg shadow-sm bg-indigo-600 text-white hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {loading ? (
                  <>
                    <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-white mr-3"></div>
                    Signing in...
                  </>
                ) : (
                  'Sign in with Email'
                )}
              </button>
            </form>
          )}

          {/* OIDC Login Button */}
          {oidcEnabled && (
            <button
              onClick={handleOIDCLogin}
              disabled={loading}
              className="w-full flex items-center justify-center px-4 py-3 border border-gray-300 rounded-lg shadow-sm bg-white text-gray-700 hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {loading ? (
                <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-indigo-600 mr-3"></div>
              ) : (
                <svg className="w-5 h-5 mr-3" viewBox="0 0 24 24">
                  <path fill="#00A4EF" d="M0 0h11.377v11.372H0z"/>
                  <path fill="#FFB900" d="M12.623 0H24v11.372H12.623z"/>
                  <path fill="#7FBA00" d="M0 12.628h11.377V24H0z"/>
                  <path fill="#F25022" d="M12.623 12.628H24V24H12.623z"/>
                </svg>
              )}
              {loading ? 'Signing in...' : 'Sign in with Microsoft'}
            </button>
          )}
          
          {/* Features */}
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
        
        {/* Footer */}
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