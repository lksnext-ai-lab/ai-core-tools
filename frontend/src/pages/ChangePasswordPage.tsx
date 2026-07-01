import { useState, useEffect, useRef } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { authService } from '../services/auth';
import { useUser } from '../contexts/UserContext';

export interface ChangePasswordPageProps {
  readonly className?: string;
}

const MIN_PASSWORD_LENGTH = 12;

function ChangePasswordPage() {
  const navigate = useNavigate();
  const { user } = useUser();

  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const successHeadingRef = useRef<HTMLHeadingElement>(null);

  // Move focus to the success heading so screen readers announce the state change.
  useEffect(() => {
    if (success && successHeadingRef.current) {
      successHeadingRef.current.focus();
    }
  }, [success]);

  const validationError = (): string | null => {
    if (newPassword.length < MIN_PASSWORD_LENGTH) {
      return `New password must be at least ${MIN_PASSWORD_LENGTH} characters.`;
    }
    if (newPassword !== confirm) {
      return 'New passwords do not match.';
    }
    if (newPassword === currentPassword) {
      return 'New password must be different from your current password.';
    }
    return null;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    const ve = validationError();
    if (ve) {
      setError(ve);
      return;
    }

    setIsLoading(true);
    try {
      await authService.changePassword(currentPassword, newPassword);
      setSuccess(true);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Password change failed. Please check your current password.');
    } finally {
      setIsLoading(false);
    }
  };

  if (success) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-gradient-to-br from-indigo-50 via-slate-50 to-blue-50 dark:from-slate-900 dark:via-slate-900 dark:to-slate-800 px-4">
        <main className="max-w-md w-full bg-white dark:bg-slate-800 rounded-2xl shadow-lg border border-slate-200 dark:border-slate-700 p-8 text-center">
          <div role="status" aria-live="polite">
            <div className="w-12 h-12 rounded-full bg-green-100 dark:bg-green-900/30 flex items-center justify-center mx-auto mb-4" aria-hidden="true">
              <svg className="w-6 h-6 text-green-600 dark:text-green-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
              </svg>
            </div>
            <h1
              ref={successHeadingRef}
              tabIndex={-1}
              className="text-xl font-bold text-slate-900 dark:text-slate-100 mb-2 focus:outline-none"
            >
              Password Changed
            </h1>
            <p className="text-sm text-slate-600 dark:text-slate-400 mb-6">
              Your password has been updated. For security, all other sessions have been signed out. Please sign in again.
            </p>
          </div>
          <button
            type="button"
            onClick={() => authService.logout().finally(() => navigate('/login', { replace: true }))}
            className="btn-login-gradient inline-flex items-center justify-center w-full px-4 py-3 rounded-xl font-semibold text-white shadow-lg"
          >
            Go to sign in
          </button>
        </main>
      </div>
    );
  }

  return (
    <div className="flex items-center justify-center min-h-screen bg-gradient-to-br from-indigo-50 via-slate-50 to-blue-50 dark:from-slate-900 dark:via-slate-900 dark:to-slate-800 px-4">
      <main className="max-w-md w-full bg-white dark:bg-slate-800 rounded-2xl shadow-lg border border-slate-200 dark:border-slate-700 p-8">
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">Change password</h1>
          <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
            Choose a new password. All other sessions will be signed out.
          </p>
        </div>

        {/* Always-rendered so screen readers receive the alert before the error fires */}
        <div
          role="alert"
          aria-live="assertive"
          id="change-password-error"
          className={error ? 'mb-4 flex items-start gap-3 rounded-xl px-4 py-3 bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800' : 'sr-only'}
        >
          {error && (
            <>
              <svg className="w-5 h-5 flex-shrink-0 mt-0.5 text-red-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9 3.75h.008v.008H12v-.008Z" />
              </svg>
              <p className="text-sm text-red-700 dark:text-red-300">{error}</p>
            </>
          )}
        </div>

        <form onSubmit={handleSubmit} className="space-y-5" noValidate>
          {/* Hidden username field — helps password managers associate the new password with this account */}
          {user?.email && (
            <input
              type="email"
              autoComplete="username"
              value={user.email}
              aria-hidden="true"
              tabIndex={-1}
              readOnly
              className="sr-only"
            />
          )}

          <div>
            <label htmlFor="current-password" className="block text-sm font-medium mb-2 text-slate-700 dark:text-slate-300">
              Current Password
            </label>
            <input
              id="current-password"
              type="password"
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              required
              aria-required="true"
              aria-invalid={error !== null}
              aria-describedby="change-password-error"
              autoComplete="current-password"
              disabled={isLoading}
              className="input-login w-full px-4 py-3 rounded-xl border bg-white dark:bg-slate-700 border-slate-200 dark:border-slate-600 text-slate-900 dark:text-slate-100 placeholder-slate-400 disabled:opacity-50 disabled:cursor-not-allowed transition-all duration-200"
            />
          </div>

          <div>
            <label htmlFor="new-password" className="block text-sm font-medium mb-2 text-slate-700 dark:text-slate-300">
              New Password
            </label>
            <input
              id="new-password"
              type="password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              required
              aria-required="true"
              aria-invalid={error !== null}
              aria-describedby="new-password-hint change-password-error"
              autoComplete="new-password"
              disabled={isLoading}
              className="input-login w-full px-4 py-3 rounded-xl border bg-white dark:bg-slate-700 border-slate-200 dark:border-slate-600 text-slate-900 dark:text-slate-100 placeholder-slate-400 disabled:opacity-50 disabled:cursor-not-allowed transition-all duration-200"
            />
            <p id="new-password-hint" className="mt-1.5 text-xs text-slate-600 dark:text-slate-300">
              Minimum {MIN_PASSWORD_LENGTH} characters
            </p>
          </div>

          <div>
            <label htmlFor="confirm-password" className="block text-sm font-medium mb-2 text-slate-700 dark:text-slate-300">
              Confirm New Password
            </label>
            <input
              id="confirm-password"
              type="password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              required
              aria-required="true"
              aria-invalid={error !== null}
              aria-describedby="change-password-error"
              autoComplete="new-password"
              disabled={isLoading}
              className="input-login w-full px-4 py-3 rounded-xl border bg-white dark:bg-slate-700 border-slate-200 dark:border-slate-600 text-slate-900 dark:text-slate-100 placeholder-slate-400 disabled:opacity-50 disabled:cursor-not-allowed transition-all duration-200"
            />
          </div>

          <button
            type="submit"
            disabled={isLoading || !currentPassword || !newPassword || !confirm}
            className="btn-login-gradient w-full flex items-center justify-center px-4 py-3 rounded-xl font-semibold text-white shadow-lg disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isLoading ? (
              <>
                <svg className="animate-spin h-5 w-5 mr-2" fill="none" viewBox="0 0 24 24" aria-hidden="true">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 0 1 8-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                Changing password...
              </>
            ) : 'Change password'}
          </button>
        </form>

        <p className="mt-6 text-sm text-center text-slate-500 dark:text-slate-400">
          <Link
            to="/apps"
            className="hover:underline"
            style={{ color: 'var(--color-primary)' }}
          >
            Cancel
          </Link>
        </p>
      </main>
    </div>
  );
}

export default ChangePasswordPage;
