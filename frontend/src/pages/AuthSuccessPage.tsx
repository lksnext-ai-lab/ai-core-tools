import { useEffect, useState, useRef } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { authService } from '../services/auth';
import { useUser } from '../contexts/UserContext';

function AuthSuccessPage() {
  const [status, setStatus] = useState<'processing' | 'success' | 'error'>('processing');
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();
  const location = useLocation();
  const { refreshUser } = useUser();
  const processedRef = useRef(false);

  useEffect(() => {
    const handleCallback = async () => {
      // Prevent multiple processing
      if (processedRef.current) {
        return;
      }
      processedRef.current = true;

      try {
        // Handle the OAuth callback
        const result = authService.handleAuthCallback();
        
        if (result.success) {
          // Refresh user data in context
          await refreshUser();
          // Redirect immediately to apps page
          navigate('/apps');
        } else {
          setStatus('error');
          setError(result.error || 'Authentication failed');
        }
      } catch (error) {
        console.error('Auth callback error:', error);
        setStatus('error');
        setError('Authentication failed');
      }
    };

    handleCallback();
  }, [refreshUser, navigate, location]);

  if (status === 'processing') {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-blue-50 to-indigo-100">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600 mx-auto mb-4"></div>
          <h2 className="text-xl font-semibold text-gray-900">Completing sign in...</h2>
          <p className="text-gray-600 mt-2">Please wait while we set up your account</p>
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