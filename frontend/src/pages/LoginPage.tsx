import { useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { authService } from '../services/auth';
import { useUser } from '../contexts/UserContext';

function LoginPage() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loginMode, setLoginMode] = useState<'OIDC' | 'FAKE' | null>(null);
  const [email, setEmail] = useState('');
  const navigate = useNavigate();
  const location = useLocation();
  const { user, refreshUser } = useUser();

  // Get the intended destination or default to /apps
  const from = location.state?.from?.pathname || '/apps';

  // Check if already authenticated
  useEffect(() => {
    if (user) {
      navigate(from, { replace: true });
    }
  }, [user, navigate, from]);

  // Check login mode on mount
  useEffect(() => {
    const checkLoginMode = async () => {
      try {
        const response = await authService.getLoginMode();
        setLoginMode(response.mode as 'OIDC' | 'FAKE');
      } catch (err) {
        console.error('Failed to check login mode:', err);
        setLoginMode('OIDC'); // Default to OIDC
      }
    };
    checkLoginMode();
  }, []);

  const handleOAuthLogin = async () => {
    try {
      setLoading(true);
      setError(null);
      await authService.login();
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
      
      // Refresh user data
      await refreshUser();
      
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
  if (user) {
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
          {loginMode === 'FAKE' && (
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

          {/* Loading state while checking mode */}
          {loginMode === null && (
            <div className="flex items-center justify-center py-8">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600"></div>
            </div>
          )}

          {/* Fake Login Form */}
          {loginMode === 'FAKE' && (
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

          {/* Google Login Button */}
          {loginMode === 'OIDC' && (
            <button
              onClick={handleOAuthLogin}
              disabled={loading}
              className="w-full flex items-center justify-center px-4 py-3 border border-gray-300 rounded-lg shadow-sm bg-white text-gray-700 hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {loading ? (
                <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-indigo-600 mr-3"></div>
              ) : (
                <svg className="w-5 h-5 mr-3" viewBox="0 0 24 24">
                  <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
                  <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
                  <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
                  <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
                </svg>
              )}
              {loading ? 'Signing in...' : 'Continue with Google'}
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