import React, { useEffect, useState } from 'react';
import { useSearchParams, Link } from 'react-router-dom';
import { configService } from '../core/ConfigService';

const VerifyEmailPage: React.FC = () => {
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token');
  const [status, setStatus] = useState<'loading' | 'success' | 'error'>('loading');
  const [message, setMessage] = useState('');

  useEffect(() => {
    if (!token) {
      setStatus('error');
      setMessage('No verification token found in the URL.');
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
          setMessage(data.message || 'Email verified successfully.');
        } else {
          setStatus('error');
          setMessage(data.detail || 'Verification failed.');
        }
      } catch {
        setStatus('error');
        setMessage('An error occurred. Please try again.');
      }
    };

    verify();
  }, [token]);

  return (
    <div className="flex items-center justify-center min-h-screen bg-gray-50">
      <div className="max-w-md w-full bg-white rounded-lg shadow p-8 text-center">
        {status === 'loading' && <p className="text-gray-600">Verifying your email...</p>}
        {status === 'success' && (
          <>
            <h2 className="text-xl font-semibold text-green-700 mb-2">Email verified!</h2>
            <p className="text-gray-600 mb-4">{message}</p>
            <Link to="/login" className="text-blue-600 hover:underline">Sign in now</Link>
          </>
        )}
        {status === 'error' && (
          <>
            <h2 className="text-xl font-semibold text-red-700 mb-2">Verification failed</h2>
            <p className="text-gray-600 mb-4">{message}</p>
            <Link to="/login" className="text-blue-600 hover:underline">Back to login</Link>
          </>
        )}
      </div>
    </div>
  );
};

export default VerifyEmailPage;
