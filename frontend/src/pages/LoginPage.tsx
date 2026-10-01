import { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate, useLocation, Link } from 'react-router-dom';
import { authService } from '../services/auth';
import { useUser } from '../contexts/UserContext';
import { useAuth } from '../auth/AuthContext';
import { useTheme } from '../themes/ThemeContext';
import { useDeploymentMode } from '../contexts/DeploymentModeContext';
import AIRobot3D from '../components/ui/AIRobot3D';

const PHRASES = [
  'Hey! Ready to build something amazing?',
  'Your agents are waiting for you...',
  'Did you know? You can chain agents as tools!',
  'Tip: Connect any LLM provider in seconds',
  'Fun fact: Your docs become AI-searchable instantly',
  'Psst... MCP lets your agents use external tools',
  'I can juggle 6 LLM providers. Can you?',
  'Still here? I could be automating things for you...',
  'Your knowledge base misses you. Just saying.',
  'Plot twist: I work while you sleep.',
];

const PHRASE_INTERVAL_MS = 8000;

function RobotGreeting() {
  const [displayText, setDisplayText] = useState('');
  const [showCursor, setShowCursor] = useState(true);
  const isSpeaking = true;
  const [bubbleKey, setBubbleKey] = useState(0);
  const [bubbleVisible, setBubbleVisible] = useState(false);
  const phraseIndexRef = useRef(0);
  const charIndexRef = useRef(0);
  const typingIntervalRef = useRef<ReturnType<typeof setInterval> | undefined>(undefined);
  const cursorTimeoutRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const rotateTransitionRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  const clearAllTimers = useCallback(() => {
    clearInterval(typingIntervalRef.current);
    clearTimeout(cursorTimeoutRef.current);
    clearTimeout(rotateTransitionRef.current);
  }, []);

  const typePhrase = useCallback((phrase: string) => {
    clearAllTimers();
    charIndexRef.current = 0;
    setDisplayText('');
    setShowCursor(true);
    setBubbleVisible(true);
    setBubbleKey((k) => k + 1);

    typingIntervalRef.current = setInterval(() => {
      charIndexRef.current++;
      if (charIndexRef.current <= phrase.length) {
        setDisplayText(phrase.slice(0, charIndexRef.current));
      } else {
        clearInterval(typingIntervalRef.current);
        cursorTimeoutRef.current = setTimeout(() => setShowCursor(false), 1500);
      }
    }, 40);
  }, [clearAllTimers]);

  useEffect(() => {
    const startDelay = setTimeout(() => {
      typePhrase(PHRASES[0]);
    }, 800);

    const rotateInterval = setInterval(() => {
      setBubbleVisible(false);
      rotateTransitionRef.current = setTimeout(() => {
        phraseIndexRef.current = (phraseIndexRef.current + 1) % PHRASES.length;
        typePhrase(PHRASES[phraseIndexRef.current]);
      }, 400);
    }, PHRASE_INTERVAL_MS);

    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        typePhrase(PHRASES[phraseIndexRef.current]);
      } else {
        clearAllTimers();
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);

    return () => {
      clearTimeout(startDelay);
      clearInterval(rotateInterval);
      clearAllTimers();
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, [typePhrase, clearAllTimers]);

  return (
    <div className="flex items-center gap-4 animate-fade-in-up-d1">
      <div className="w-36 h-44 flex-shrink-0">
        <AIRobot3D isSpeaking={isSpeaking} disableParallax />
      </div>
      <div className="w-[260px] flex-shrink-0">
        <div
          key={bubbleKey}
          className={`speech-bubble-right speech-bubble-emerge relative px-4 py-3 rounded-lg bg-white transition-opacity duration-300 ${
            bubbleVisible ? 'opacity-100' : 'opacity-0'
          }`}
        >
          <p className="text-fg-secondary text-sm font-medium min-h-[1.25rem] leading-relaxed">
            {displayText}
            {showCursor && (
              <span
                className="ml-0.5 inline-block w-[2px] h-4 align-middle bg-accent"
              />
            )}
          </p>
        </div>
      </div>
    </div>
  );
}

// null = no error; 'both' = server credential rejection (avoids hinting which field was wrong)
type LoginErrorField = 'email' | 'password' | 'both' | null;

function LoginPage() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [errorField, setErrorField] = useState<LoginErrorField>(null);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [shakeError, setShakeError] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  const { user, refreshUser } = useUser();
  const auth = useAuth();
  const { theme } = useTheme();

  const { isSaasMode, isLoading: configLoading, authMode } = useDeploymentMode();

  const from = (location.state as { from?: { pathname?: string } } | null)?.from?.pathname ?? '/apps';

  useEffect(() => {
    if (user !== null || auth.isAuthenticated) {
      navigate(from, { replace: true });
    }
  }, [user, auth.isAuthenticated, navigate, from]);

  const triggerError = (message: string, field: LoginErrorField = null) => {
    setError(message);
    setErrorField(field);
    setShakeError(true);
    setTimeout(() => setShakeError(false), 600);
  };

  const handleOIDCLogin = async () => {
    try {
      setLoading(true);
      setError(null);
      await auth.login();
    } catch (err) {
      triggerError(err instanceof Error ? err.message : 'Login failed');
      setLoading(false);
    }
  };

  const handleLocalLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email || !password) {
      triggerError('Please enter your email and password');
      return;
    }
    try {
      setLoading(true);
      setError(null);
      setErrorField(null);
      await authService.localLogin(email, password);
      await refreshUser();
      navigate(from, { replace: true });
    } catch (err: unknown) {
      triggerError(err instanceof Error ? err.message : 'Login failed', 'both');
      setLoading(false);
    }
  };

  if (user !== null || auth.isAuthenticated) {
    return null;
  }

  return (
    // Design v3 login: sign-in column (left) + brand panel with the robot (right)
    <div className="min-h-screen flex bg-canvas text-fg dark:bg-canvas-dark dark:text-fg-dark">
      <main className="flex-1 min-w-0 flex flex-col items-center justify-center px-6 py-10 sm:px-10 overflow-y-auto bg-gradient-to-b from-canvas-alt to-surface dark:from-canvas-alt-dark dark:to-surface-dark">
        <div className="w-full max-w-[400px]">
        <div className="flex items-center justify-center gap-2.5 mb-10 animate-fade-in-up">
          {theme.logo ? (
            <img src={theme.logo} alt={theme.name} className="w-10 h-auto" />
          ) : (
            <div className="h-10 w-10 rounded-lg flex items-center justify-center bg-ink dark:bg-ink-dark">
              <svg className="w-6 h-6 text-ink-on dark:text-ink-on-dark" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904 9 18.75l-.813-2.846a4.5 4.5 0 0 0-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 0 0 3.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 0 0 3.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 0 0-3.09 3.09ZM18.259 8.715 18 9.75l-.259-1.035a3.375 3.375 0 0 0-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 0 0 2.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 0 0 2.455 2.456L21.75 6l-1.036.259a3.375 3.375 0 0 0-2.455 2.456ZM16.894 20.567 16.5 21.75l-.394-1.183a2.25 2.25 0 0 0-1.423-1.423L13.5 18.75l1.183-.394a2.25 2.25 0 0 0 1.423-1.423l.394-1.183.394 1.183a2.25 2.25 0 0 0 1.423 1.423l1.183.394-1.183.394a2.25 2.25 0 0 0-1.423 1.423Z" />
              </svg>
            </div>
          )}
          <span className="font-display text-[22px] font-medium tracking-[-0.01em] text-fg dark:text-fg-dark">
            {theme.name || 'Mattin AI'}
          </span>
        </div>

        <div className="w-full animate-fade-in-up-d2">
          <div className="rounded-lg border px-[30px] py-8 space-y-5 bg-surface border-line dark:bg-surface-dark dark:border-line-dark">
            <div className="text-center">
              <h2 className="font-display text-2xl font-normal tracking-[-0.02em] text-fg dark:text-fg-dark">
                Welcome back
              </h2>
              <p className="mt-1.5 text-[13.5px] text-fg-tertiary dark:text-fg-tertiary-dark">
                Sign in to{' '}
                <span className="font-medium text-fg underline decoration-accent underline-offset-[3px] dark:text-fg-dark dark:decoration-accent-dark">
                  {theme.name || 'Mattin AI'}
                </span>
              </p>
            </div>

            {/* Always-rendered so screen readers receive the alert before the error fires */}
            <div
              role="alert"
              aria-live="assertive"
              id="login-error"
              className={error ? `flex items-start gap-3 rounded-lg px-4 py-3 bg-error-bg border border-error-border dark:bg-error-bg-dark dark:border-error-border-dark ${shakeError ? 'animate-shake' : ''}` : 'sr-only'}
            >
              {error && (
                <>
                  <svg className="w-5 h-5 flex-shrink-0 mt-0.5 text-error dark:text-error-dark" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} aria-hidden="true">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9 3.75h.008v.008H12v-.008Z" />
                  </svg>
                  <div>
                    <p className="text-sm font-medium text-error-strong dark:text-error-strong-dark">Login Error</p>
                    <p className="text-sm mt-0.5 text-error dark:text-error-dark">{error}</p>
                  </div>
                </>
              )}
            </div>

            {configLoading && (
              <div className="flex justify-center py-4" aria-label="Loading sign-in options" aria-busy="true">
                <svg className="animate-spin h-6 w-6 text-fg-faint dark:text-fg-faint-dark" fill="none" viewBox="0 0 24 24" aria-hidden="true">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 0 1 8-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
              </div>
            )}

            {!configLoading && authMode === 'local' && (
              <form onSubmit={handleLocalLogin} className="space-y-4" noValidate>
                <div>
                  <label htmlFor="email" className="block text-sm font-medium mb-2 text-fg dark:text-fg-dark">
                    Email Address
                  </label>
                  <div className="relative">
                    <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3.5 text-fg-tertiary dark:text-fg-tertiary-dark" aria-hidden="true">
                      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.6}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M21.75 6.75v10.5a2.25 2.25 0 0 1-2.25 2.25h-15a2.25 2.25 0 0 1-2.25-2.25V6.75m19.5 0A2.25 2.25 0 0 0 19.5 4.5h-15a2.25 2.25 0 0 0-2.25 2.25m19.5 0v.243a2.25 2.25 0 0 1-1.07 1.916l-7.5 4.615a2.25 2.25 0 0 1-2.36 0L3.32 8.91a2.25 2.25 0 0 1-1.07-1.916V6.75" />
                      </svg>
                    </div>
                    <input
                      id="email"
                      type="email"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      placeholder="user@example.com"
                      disabled={loading}
                      required
                      autoComplete="email"
                      aria-required="true"
                      aria-invalid={errorField === 'email' || errorField === 'both'}
                      aria-describedby="login-error"
                      className="w-full pl-11 pr-4 py-3 text-sm rounded-lg border bg-surface border-line-strong text-fg placeholder:text-fg-faint focus:outline-none focus:border-ink focus:ring-1 focus:ring-ink dark:bg-surface-dark dark:border-line-strong-dark dark:text-fg-dark dark:placeholder:text-fg-faint-dark dark:focus:border-ink-dark dark:focus:ring-ink-dark disabled:opacity-50 disabled:cursor-not-allowed transition-colors duration-200"
                    />
                  </div>
                </div>
                <div>
                  <label htmlFor="password" className="block text-sm font-medium mb-2 text-fg dark:text-fg-dark">
                    Password
                  </label>
                  <input
                    id="password"
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="••••••••"
                    disabled={loading}
                    required
                    autoComplete="current-password"
                    aria-required="true"
                    aria-invalid={errorField === 'password' || errorField === 'both'}
                    aria-describedby="login-error"
                    className="w-full px-4 py-3 text-sm rounded-lg border bg-surface border-line-strong text-fg placeholder:text-fg-faint focus:outline-none focus:border-ink focus:ring-1 focus:ring-ink dark:bg-surface-dark dark:border-line-strong-dark dark:text-fg-dark dark:placeholder:text-fg-faint-dark dark:focus:border-ink-dark dark:focus:ring-ink-dark disabled:opacity-50 disabled:cursor-not-allowed transition-colors duration-200"
                  />
                </div>
                <button
                  type="submit"
                  disabled={loading || !email || !password}
                  className="w-full flex items-center justify-center px-4 py-3 rounded-lg text-sm font-medium bg-ink text-ink-on hover:bg-ink/85 focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-focus dark:bg-ink-dark dark:text-ink-on-dark dark:hover:bg-ink-dark/85 dark:focus-visible:ring-focus-dark dark:focus-visible:ring-offset-surface-dark transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {loading ? (
                    <>
                      <svg className="animate-spin h-5 w-5 mr-2" fill="none" viewBox="0 0 24 24" aria-hidden="true">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 0 1 8-8V0C5.373 0 0 5.373 0 12h4z" />
                      </svg>
                      Signing in...
                    </>
                  ) : 'Sign in'}
                </button>
              </form>
            )}

            {!configLoading && authMode === 'oidc' && (
              <button
                type="button"
                onClick={handleOIDCLogin}
                disabled={loading}
                className="w-full flex items-center justify-center gap-2.5 px-[18px] py-[13px] rounded-lg border text-sm font-medium bg-surface border-line-strong text-fg hover:bg-canvas-alt focus:outline-none focus-visible:ring-2 focus-visible:ring-focus dark:bg-surface-dark dark:border-line-strong-dark dark:text-fg-dark dark:hover:bg-canvas-alt-dark dark:focus-visible:ring-focus-dark transition-colors duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {loading ? (
                  <svg className="animate-spin h-5 w-5" fill="none" viewBox="0 0 24 24" aria-hidden="true">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 0 1 8-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                ) : (
                  <svg className="w-[17px] h-[17px]" viewBox="0 0 24 24" aria-hidden="true">
                    <path fill="#00A4EF" d="M0 0h11.377v11.372H0z" />
                    <path fill="#FFB900" d="M12.623 0H24v11.372H12.623z" />
                    <path fill="#7FBA00" d="M0 12.628h11.377V24H0z" />
                    <path fill="#F25022" d="M12.623 12.628H24V24H12.623z" />
                  </svg>
                )}
                {loading ? 'Signing in...' : 'Sign in with Microsoft'}
              </button>
            )}

            {!configLoading && isSaasMode && (
              <div className="mt-4 text-center space-y-2">
                <p className="text-sm text-fg-tertiary dark:text-fg-tertiary-dark">
                  Don&apos;t have an account?{' '}
                  <Link
                    to="/register"
                    className="font-medium text-fg underline decoration-accent underline-offset-[3px] hover:text-accent dark:text-fg-dark dark:decoration-accent-dark dark:hover:text-accent-dark"
                  >
                    Create one
                  </Link>
                </p>
                <p className="text-sm text-fg-tertiary dark:text-fg-tertiary-dark">
                  <Link
                    to="/password-reset/request"
                    className="text-fg underline decoration-accent underline-offset-[3px] hover:text-accent dark:text-fg-dark dark:decoration-accent-dark dark:hover:text-accent-dark"
                  >
                    Forgot your password?
                  </Link>
                </p>
              </div>
            )}

            {/* Self-hosted LOCAL: no public reset link — admin-initiated only */}
            {!configLoading && !isSaasMode && authMode === 'local' && (
              <p className="text-xs text-center text-fg-faint dark:text-fg-faint-dark mt-2">
                Forgot your password? Contact your administrator.
              </p>
            )}
          </div>
        </div>

        <div className="mt-[22px] text-center animate-fade-in-up-d3">
          <p className="text-xs text-fg-faint dark:text-fg-faint-dark">
            By signing in, you agree to our{' '}
            <button type="button" onClick={() => undefined} className="text-fg underline decoration-accent underline-offset-[3px] hover:text-accent bg-transparent border-0 p-0 cursor-pointer dark:text-fg-dark dark:decoration-accent-dark dark:hover:text-accent-dark">
              Terms of Service
            </button>
            {' '}and{' '}
            <button type="button" onClick={() => undefined} className="text-fg underline decoration-accent underline-offset-[3px] hover:text-accent bg-transparent border-0 p-0 cursor-pointer dark:text-fg-dark dark:decoration-accent-dark dark:hover:text-accent-dark">
              Privacy Policy
            </button>
          </p>
        </div>
        </div>
      </main>

      {/* Brand panel ("welcome image" slot in the design) — the robot lives here */}
      <aside className="hidden lg:flex flex-1 min-w-0 items-center justify-center overflow-hidden px-10 bg-bronze-bg dark:bg-bronze-bg-dark">
        <RobotGreeting />
      </aside>
    </div>
  );
}

export default LoginPage;
