import { useState, useEffect, useRef } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { AlertTriangle } from 'lucide-react';
import { authService } from '../services/auth';
import { ButtonApp } from '../components/ui/ButtonApp';
import { FormField } from '../components/ui/FormField';

export interface SetPasswordPageProps {
  readonly className?: string;
}

const MIN_PASSWORD_LENGTH = 12;

function SetPasswordPage() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token') ?? '';

  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const successHeadingRef = useRef<HTMLHeadingElement>(null);
  const invalidHeadingRef = useRef<HTMLHeadingElement>(null);

  // Move focus to success/invalid headings so screen readers announce the state change.
  useEffect(() => {
    if (success && successHeadingRef.current) {
      successHeadingRef.current.focus();
    }
  }, [success]);

  useEffect(() => {
    if (!token && invalidHeadingRef.current) {
      invalidHeadingRef.current.focus();
    }
  }, [token]);

  const validationError = (): string | null => {
    if (password.length < MIN_PASSWORD_LENGTH) {
      return `Password must be at least ${MIN_PASSWORD_LENGTH} characters.`;
    }
    if (password !== confirm) {
      return 'Passwords do not match.';
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
      await authService.setPassword(token, password);
      setSuccess(true);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Set password failed. The link may have expired.');
    } finally {
      setIsLoading(false);
    }
  };

  if (!token) {
    return (
      <div className="flex items-center justify-center min-h-screen px-4 text-fg bg-gradient-to-b from-canvas-alt to-surface dark:text-fg-dark dark:from-canvas-alt-dark dark:to-surface-dark">
        <main className="max-w-md w-full rounded-lg border px-[30px] py-8 bg-surface border-line dark:bg-surface-dark dark:border-line-dark text-center">
          <div role="status" aria-live="polite">
            <div className="w-12 h-12 rounded-full border bg-error-bg border-error-border dark:bg-error-bg-dark dark:border-error-border-dark flex items-center justify-center mx-auto mb-4" aria-hidden="true">
              <svg className="w-6 h-6 text-error dark:text-error-dark" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9 3.75h.008v.008H12v-.008Z" />
              </svg>
            </div>
            <h1
              ref={invalidHeadingRef}
              tabIndex={-1}
              className="font-display text-xl font-normal tracking-[-0.02em] text-fg dark:text-fg-dark mb-2 focus:outline-none"
            >
              Invalid Link
            </h1>
            <p className="text-[13.5px] text-fg-tertiary dark:text-fg-tertiary-dark mb-6">
              This set-password link is missing a token. Please use the full link from your invitation email.
            </p>
          </div>
          <Link
            to="/login"
            className="inline-flex items-center gap-2 text-sm font-medium text-fg underline decoration-accent underline-offset-[3px] hover:text-accent dark:text-fg-dark dark:decoration-accent-dark dark:hover:text-accent-dark"
          >
            Back to sign in
          </Link>
        </main>
      </div>
    );
  }

  if (success) {
    return (
      <div className="flex items-center justify-center min-h-screen px-4 text-fg bg-gradient-to-b from-canvas-alt to-surface dark:text-fg-dark dark:from-canvas-alt-dark dark:to-surface-dark">
        <main className="max-w-md w-full rounded-md border px-[30px] py-8 bg-surface border-line dark:bg-surface-dark dark:border-line-dark text-center">
          <div role="status" aria-live="polite">
            <div className="w-12 h-12 rounded-full border bg-success-bg border-success-border dark:bg-success-bg-dark dark:border-success-border-dark flex items-center justify-center mx-auto mb-4" aria-hidden="true">
              <svg className="w-6 h-6 text-success dark:text-success-dark" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
              </svg>
            </div>
            <h1
              ref={successHeadingRef}
              tabIndex={-1}
              className="font-display text-xl font-normal tracking-[-0.02em] text-fg dark:text-fg-dark mb-2 focus:outline-none"
            >
              Password Set
            </h1>
            <p className="text-[13.5px] text-fg-tertiary dark:text-fg-tertiary-dark mb-6">
              Your password has been set successfully. You can now sign in.
            </p>
          </div>
          <Link
            to="/login"
            className="inline-flex items-center justify-center w-full px-4 py-3 rounded-lg text-[15px] font-medium border border-transparent bg-ink text-ink-on hover:bg-ink-hover dark:bg-ink-dark dark:text-ink-on-dark dark:hover:bg-ink-hover-dark transition-colors"
          >
            Go to sign in
          </Link>
        </main>
      </div>
    );
  }

  return (
    <div className="flex items-center justify-center min-h-screen px-4 text-fg bg-gradient-to-b from-canvas-alt to-surface dark:text-fg-dark dark:from-canvas-alt-dark dark:to-surface-dark">
      <main className="max-w-md w-full rounded-md border px-[30px] py-8 bg-surface border-line dark:bg-surface-dark dark:border-line-dark">
        <div className="mb-6">
          <h1 className="font-display text-2xl font-normal tracking-[-0.02em] text-fg dark:text-fg-dark">Set your password</h1>
          <p className="mt-1.5 text-[13.5px] text-fg-tertiary dark:text-fg-tertiary-dark">
            Choose a strong password to activate your account.
          </p>
        </div>

        {/* Always-rendered so screen readers receive the alert before the error fires */}
        <div
          role="alert"
          aria-live="assertive"
          id="set-password-error"
          className={error ? 'mb-4 flex rounded-lg p-4 bg-error-bg border border-error-border dark:bg-error-bg-dark dark:border-error-border-dark' : 'sr-only'}
        >
          {error && (
            <>
              <span className="mr-3 shrink-0 text-error dark:text-error-dark" aria-hidden="true">
                <AlertTriangle className="w-5 h-5" />
              </span>
              <p className="flex-1 text-sm text-error dark:text-error-dark">{error}</p>
            </>
          )}
        </div>

        <form onSubmit={handleSubmit} className="space-y-5" noValidate>
          {/* Hidden username field — helps password managers; email unavailable on token-based flow so value is omitted */}
          <FormField
            id="username"
            type="email"
            autoComplete="username"
            readOnly
            ariaHidden
            tabIndex={-1}
            className="sr-only"
          />

          <FormField
            id="new-password"
            label="New Password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            ariaRequired
            ariaInvalid={error !== null}
            ariaDescribedBy="set-password-error"
            autoComplete="new-password"
            disabled={isLoading}
            helpText={`Minimum ${MIN_PASSWORD_LENGTH} characters`}
          />

          <FormField
            id="confirm-password"
            label="Confirm Password"
            type="password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            required
            ariaRequired
            ariaInvalid={error !== null}
            ariaDescribedBy="set-password-error"
            autoComplete="new-password"
            disabled={isLoading}
          />

          <ButtonApp
            type="submit"
            label={isLoading ? 'Setting password...' : 'Set password'}
            disabled={!password || !confirm}
            loading={isLoading}
            size="spacious"
            className="w-full"
          />
        </form>

        <p className="mt-6 text-sm text-center text-fg-tertiary dark:text-fg-tertiary-dark">
          <Link
            to="/login"
            className="font-medium text-fg underline decoration-accent underline-offset-[3px] hover:text-accent dark:text-fg-dark dark:decoration-accent-dark dark:hover:text-accent-dark"
          >
            Back to sign in
          </Link>
        </p>
      </main>
    </div>
  );
}

export default SetPasswordPage;
