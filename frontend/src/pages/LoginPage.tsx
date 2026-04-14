import { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate, useLocation, Link } from 'react-router-dom';
import { authService } from '../services/auth';
import { useUser } from '../contexts/UserContext';
import { useAuth } from '../auth/AuthContext';
import { useTheme } from '../themes/ThemeContext';
import { useDeploymentMode } from '../contexts/DeploymentModeContext';
import Particles from '../components/ui/Particles';
import AIRobot3D from '../components/ui/AIRobot3D';

/* ─────────────────────── Feature cards data ─────────────────────── */

const FEATURES = [
  {
    title: 'Intelligent Agents',
    desc: 'Design AI agents with custom prompts, skills, and memory',
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M9.75 3.104v5.714a2.25 2.25 0 0 1-.659 1.591L5 14.5M9.75 3.104c-.251.023-.501.05-.75.082m.75-.082a24.301 24.301 0 0 1 4.5 0m0 0v5.714a2.25 2.25 0 0 0 .659 1.591L19 14.5m-4.75-11.396c.251.023.501.05.75.082M12 21a8.966 8.966 0 0 0 5.982-2.275M12 21a8.966 8.966 0 0 1-5.982-2.275M15.75 3.186a24.279 24.279 0 0 1 2.226.396M6.024 3.582a24.285 24.285 0 0 1 2.226-.396" />
      </svg>
    ),
    color: '#3b82f6',
  },
  {
    title: 'RAG Knowledge',
    desc: 'Connect documents and websites for AI-powered search',
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M20.25 6.375c0 2.278-3.694 4.125-8.25 4.125S3.75 8.653 3.75 6.375m16.5 0c0-2.278-3.694-4.125-8.25-4.125S3.75 4.097 3.75 6.375m16.5 0v11.25c0 2.278-3.694 4.125-8.25 4.125s-8.25-1.847-8.25-4.125V6.375" />
      </svg>
    ),
    color: '#8b5cf6',
  },
  {
    title: 'Multi-LLM',
    desc: 'OpenAI, Anthropic, Mistral, Azure, Google & more',
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904 9 18.75l-.813-2.846a4.5 4.5 0 0 0-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 0 0 3.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 0 0 3.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 0 0-3.09 3.09ZM18.259 8.715 18 9.75l-.259-1.035a3.375 3.375 0 0 0-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 0 0 2.455-2.456L18 2.25" />
      </svg>
    ),
    color: '#06b6d4',
  },
  {
    title: 'MCP Protocol',
    desc: 'Agents use external tools via MCP, or serve as MCP endpoints',
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M13.19 8.688a4.5 4.5 0 0 1 1.242 7.244l-4.5 4.5a4.5 4.5 0 0 1-6.364-6.364l1.757-1.757m13.35-.622 1.757-1.757a4.5 4.5 0 0 0-6.364-6.364l-4.5 4.5a4.5 4.5 0 0 0 1.242 7.244" />
      </svg>
    ),
    color: '#f59e0b',
  },
];

/* ─────────────────── Robot greeting with rotating phrases ─────────────────── */

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

    // Schedule rotating phrases
    const rotateInterval = setInterval(() => {
      setBubbleVisible(false);
      rotateTransitionRef.current = setTimeout(() => {
        phraseIndexRef.current = (phraseIndexRef.current + 1) % PHRASES.length;
        typePhrase(PHRASES[phraseIndexRef.current]);
      }, 400);
    }, PHRASE_INTERVAL_MS);

    // Pause/resume typing animation on tab visibility change
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        // Tab is visible again: restart typing current phrase cleanly
        typePhrase(PHRASES[phraseIndexRef.current]);
      } else {
        // Tab is hidden: stop all timers to avoid throttled interval buildup
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
    <div className="flex items-center gap-3 animate-fade-in-up-d1">
      {/* Robot — fixed size, never moves */}
      <div className="w-24 h-28 flex-shrink-0">
        <AIRobot3D isSpeaking={isSpeaking} disableParallax />
      </div>

      {/* Speech bubble wrapper — fixed width so layout doesn't shift */}
      <div className="w-[260px] flex-shrink-0">
        <div
          key={bubbleKey}
          className={`speech-bubble-right speech-bubble-emerge relative px-4 py-3 rounded-2xl bg-white shadow-lg border border-slate-100 transition-opacity duration-300 ${
            bubbleVisible ? 'opacity-100' : 'opacity-0'
          }`}
        >
          <p className="text-slate-700 text-sm font-medium min-h-[1.25rem] leading-relaxed">
            {displayText}
            {showCursor && (
              <span
                className="ml-0.5 inline-block w-[2px] h-4 align-middle"
                style={{ backgroundColor: 'var(--color-primary)' }}
              />
            )}
          </p>
        </div>
      </div>
    </div>
  );
}

/* ─────────────────────────── LoginPage ─────────────────────────── */

function LoginPage() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [shakeError, setShakeError] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  const { user, refreshUser } = useUser();
  const auth = useAuth();
  const { theme } = useTheme();

  const { isSaasMode } = useDeploymentMode();
  const runtimeConfig = (globalThis as unknown as Record<string, Record<string, string>>).__RUNTIME_CONFIG__;
  const oidcEnabled = runtimeConfig?.VITE_OIDC_ENABLED === undefined
    ? import.meta.env.VITE_OIDC_ENABLED === 'true'
    : runtimeConfig.VITE_OIDC_ENABLED === 'true';

  const from = location.state?.from?.pathname || '/apps';

  useEffect(() => {
    if (user || auth.isAuthenticated) {
      navigate(from, { replace: true });
    }
  }, [user, auth.isAuthenticated, navigate, from]);

  const triggerError = (message: string) => {
    setError(message);
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
      await authService.localLogin(email, password);
      refreshUser();
      navigate(from, { replace: true });
    } catch (err: unknown) {
      triggerError(err instanceof Error ? err.message : 'Login failed');
      setLoading(false);
    }
  };

  const handleFakeLogin = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!email?.includes('@')) {
      triggerError('Please enter a valid email address');
      return;
    }

    try {
      setLoading(true);
      setError(null);
      await authService.fakeLogin(email);
      refreshUser();
      navigate(from, { replace: true });
    } catch (err: unknown) {
      const errorMessage = err instanceof Error ? err.message : 'Login failed';
      if (errorMessage.includes('not found')) {
        triggerError('User not found. Please contact an administrator.');
      } else {
        triggerError(errorMessage);
      }
      setLoading(false);
    }
  };

  if (user || auth.isAuthenticated) {
    return null;
  }

  return (
    <div className="min-h-screen relative overflow-hidden bg-gradient-to-br from-indigo-50 via-slate-50 to-blue-50">
      {/* Animated background blobs */}
      <div aria-hidden="true" className="pointer-events-none absolute inset-0 overflow-hidden">
        <div
          className="animate-blob-drift-a absolute -top-32 -right-32 h-96 w-96 rounded-full opacity-[0.18] blur-3xl"
          style={{ backgroundColor: 'var(--color-primary)' }}
        />
        <div
          className="animate-blob-drift-b absolute -bottom-32 -left-32 h-[28rem] w-[28rem] rounded-full opacity-[0.12] blur-3xl"
          style={{ backgroundColor: '#7c3aed' }}
        />
        <div
          className="animate-blob-drift-a absolute top-1/3 left-1/2 -translate-x-1/2 h-72 w-72 rounded-full opacity-[0.10] blur-3xl"
          style={{ backgroundColor: '#0ea5e9' }}
        />
      </div>

      {/* Subtle particles */}
      <div className="absolute inset-0 opacity-30">
        <Particles
          particleCount={80}
          particleSpread={12}
          speed={0.04}
          particleColors={['#6366f1', '#8b5cf6', '#3b82f6', '#06b6d4']}
          alphaParticles
          particleBaseSize={60}
          sizeRandomness={0.8}
          cameraDistance={30}
          disableRotation
          className="absolute inset-0"
        />
      </div>

      {/* Main content */}
      <div className="relative z-10 min-h-screen flex flex-col items-center justify-center px-4 py-8 sm:px-6">
        {/* Logo + brand — larger for brand visibility */}
        <div className="flex items-center gap-4 mb-8 animate-fade-in-up">
          {theme.logo ? (
            <img src={theme.logo} alt={theme.name} className="h-14 w-auto" />
          ) : (
            <div
              className="h-14 w-14 rounded-2xl flex items-center justify-center shadow-lg"
              style={{ backgroundColor: 'var(--color-primary)' }}
            >
              <svg className="w-7 h-7 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904 9 18.75l-.813-2.846a4.5 4.5 0 0 0-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 0 0 3.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 0 0 3.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 0 0-3.09 3.09ZM18.259 8.715 18 9.75l-.259-1.035a3.375 3.375 0 0 0-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 0 0 2.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 0 0 2.455 2.456L21.75 6l-1.036.259a3.375 3.375 0 0 0-2.455 2.456ZM16.894 20.567 16.5 21.75l-.394-1.183a2.25 2.25 0 0 0-1.423-1.423L13.5 18.75l1.183-.394a2.25 2.25 0 0 0 1.423-1.423l.394-1.183.394 1.183a2.25 2.25 0 0 0 1.423 1.423l1.183.394-1.183.394a2.25 2.25 0 0 0-1.423 1.423Z" />
              </svg>
            </div>
          )}
          <span className="text-slate-800 text-2xl font-bold tracking-tight">
            {theme.name || 'Mattin AI'}
          </span>
        </div>

        {/* Robot greeting — robot left, speech bubble right */}
        <div className="mb-6">
          <RobotGreeting />
        </div>

        {/* Glass card — login form */}
        <div className="w-full max-w-sm animate-fade-in-up-d2">
          <div className="card-login-shimmer backdrop-blur-2xl rounded-2xl shadow-xl border p-7 space-y-5 bg-white/80 border-slate-200/60 shadow-slate-200/50">
            {/* Title */}
            <div className="text-center">
              <h2 className="text-xl font-bold text-slate-900">
                Welcome back
              </h2>
              <p className="mt-1 text-sm text-slate-500">
                Sign in to{' '}
                <span className="font-medium" style={{ color: 'var(--color-primary)' }}>
                  {theme.name || 'Mattin AI'}
                </span>
              </p>
            </div>

            {/* Dev mode badge */}
            {!oidcEnabled && (
              <div className="flex justify-center">
                <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium bg-amber-100 text-amber-700">
                  <span className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse" />{' '}Dev mode
                </span>
              </div>
            )}

            {/* Error alert */}
            {error && (
              <div
                className={`flex items-start gap-3 rounded-xl px-4 py-3 bg-red-50 border border-red-200 ${
                  shakeError ? 'animate-shake' : ''
                }`}
              >
                <svg className="w-5 h-5 flex-shrink-0 mt-0.5 text-red-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9 3.75h.008v.008H12v-.008Z" />
                </svg>
                <div>
                  <p className="text-sm font-medium text-red-800">Login Error</p>
                  <p className="text-sm mt-0.5 text-red-600">{error}</p>
                </div>
              </div>
            )}

            {/* SaaS LOCAL mode — email + password form */}
            {!oidcEnabled && isSaasMode && (
              <form onSubmit={handleLocalLogin} className="space-y-4">
                <div>
                  <label htmlFor="email" className="block text-sm font-medium mb-2 text-slate-700">Email Address</label>
                  <div className="relative">
                    <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3.5 text-slate-400">
                      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.6}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M21.75 6.75v10.5a2.25 2.25 0 0 1-2.25 2.25h-15a2.25 2.25 0 0 1-2.25-2.25V6.75m19.5 0A2.25 2.25 0 0 0 19.5 4.5h-15a2.25 2.25 0 0 0-2.25 2.25m19.5 0v.243a2.25 2.25 0 0 1-1.07 1.916l-7.5 4.615a2.25 2.25 0 0 1-2.36 0L3.32 8.91a2.25 2.25 0 0 1-1.07-1.916V6.75" />
                      </svg>
                    </div>
                    <input id="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)}
                      placeholder="user@example.com" disabled={loading} required
                      className="input-login w-full pl-11 pr-4 py-3 rounded-xl border bg-white border-slate-200 text-slate-900 placeholder-slate-400 disabled:opacity-50 disabled:cursor-not-allowed transition-all duration-200"
                    />
                  </div>
                </div>
                <div>
                  <label htmlFor="password" className="block text-sm font-medium mb-2 text-slate-700">Password</label>
                  <input id="password" type="password" value={password} onChange={(e) => setPassword(e.target.value)}
                    placeholder="••••••••" disabled={loading} required
                    className="input-login w-full px-4 py-3 rounded-xl border bg-white border-slate-200 text-slate-900 placeholder-slate-400 disabled:opacity-50 disabled:cursor-not-allowed transition-all duration-200"
                  />
                </div>
                <button type="submit" disabled={loading || !email || !password}
                  className="btn-login-gradient w-full flex items-center justify-center px-4 py-3 rounded-xl font-semibold text-white shadow-lg disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {loading ? (
                    <><svg className="animate-spin h-5 w-5 mr-2" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 0 1 8-8V0C5.373 0 0 5.373 0 12h4z" /></svg>Signing in...</>
                  ) : 'Sign in'}
                </button>
              </form>
            )}

            {/* FAKE mode — email-only form (development) */}
            {!oidcEnabled && !isSaasMode && (
              <form onSubmit={handleFakeLogin} className="space-y-4">
                <div>
                  <label htmlFor="email" className="block text-sm font-medium mb-2 text-slate-700">Email Address</label>
                  <div className="relative">
                    <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3.5 text-slate-400">
                      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.6}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M21.75 6.75v10.5a2.25 2.25 0 0 1-2.25 2.25h-15a2.25 2.25 0 0 1-2.25-2.25V6.75m19.5 0A2.25 2.25 0 0 0 19.5 4.5h-15a2.25 2.25 0 0 0-2.25 2.25m19.5 0v.243a2.25 2.25 0 0 1-1.07 1.916l-7.5 4.615a2.25 2.25 0 0 1-2.36 0L3.32 8.91a2.25 2.25 0 0 1-1.07-1.916V6.75" />
                      </svg>
                    </div>
                    <input id="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)}
                      placeholder="user@example.com" disabled={loading} required
                      className="input-login w-full pl-11 pr-4 py-3 rounded-xl border bg-white border-slate-200 text-slate-900 placeholder-slate-400 disabled:opacity-50 disabled:cursor-not-allowed transition-all duration-200"
                    />
                  </div>
                </div>
                <button type="submit" disabled={loading || !email}
                  className="btn-login-gradient w-full flex items-center justify-center px-4 py-3 rounded-xl font-semibold text-white shadow-lg disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {loading ? (
                    <><svg className="animate-spin h-5 w-5 mr-2" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 0 1 8-8V0C5.373 0 0 5.373 0 12h4z" /></svg>Signing in...</>
                  ) : 'Sign in with Email'}
                </button>
              </form>
            )}

            {/* OIDC Login Button */}
            {oidcEnabled && (
              <button
                onClick={handleOIDCLogin}
                disabled={loading}
                className="w-full flex items-center justify-center gap-3 px-4 py-3.5 rounded-xl border-2 font-semibold border-slate-200 bg-white text-slate-700 hover:bg-slate-50 hover:border-[var(--color-primary)] hover:shadow-md transition-all duration-200 active:scale-[0.97] disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {loading ? (
                  <svg className="animate-spin h-5 w-5" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 0 1 8-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                ) : (
                  <svg className="w-5 h-5" viewBox="0 0 24 24">
                    <path fill="#00A4EF" d="M0 0h11.377v11.372H0z" />
                    <path fill="#FFB900" d="M12.623 0H24v11.372H12.623z" />
                    <path fill="#7FBA00" d="M0 12.628h11.377V24H0z" />
                    <path fill="#F25022" d="M12.623 12.628H24V24H12.623z" />
                  </svg>
                )}
                {loading ? 'Signing in...' : 'Sign in with Microsoft'}
              </button>
            )}
          {isSaasMode && (
            <div className="mt-4 text-center space-y-2">
              <p className="text-sm text-slate-500">
                Don't have an account?{' '}
                <Link to="/register" className="font-medium hover:underline" style={{ color: 'var(--color-primary)' }}>
                  Create one
                </Link>
              </p>
              <p className="text-sm text-slate-500">
                <Link to="/password-reset/request" className="hover:underline" style={{ color: 'var(--color-primary)' }}>
                  Forgot your password?
                </Link>
              </p>
            </div>
          )}
          </div>
        </div>

        {/* Feature cards — 2x2 grid */}
        <div className="grid grid-cols-2 gap-3 mt-8 max-w-lg w-full animate-fade-in-up-d3">
          {FEATURES.map((f) => (
            <div
              key={f.title}
              className="flex items-start gap-3 px-4 py-3 rounded-xl bg-white/60 border border-slate-200/60 backdrop-blur-sm"
            >
              <div
                className="flex-shrink-0 w-8 h-8 rounded-lg flex items-center justify-center mt-0.5"
                style={{ backgroundColor: `${f.color}15`, color: f.color }}
              >
                {f.icon}
              </div>
              <div className="min-w-0">
                <p className="text-sm font-semibold text-slate-700">{f.title}</p>
                <p className="text-xs text-slate-400 leading-snug">{f.desc}</p>
              </div>
            </div>
          ))}
        </div>

        {/* Legal footer */}
        <div className="mt-8 text-center animate-fade-in-up-d3">
          <p className="text-xs text-slate-400">
            By signing in, you agree to our{' '}
            <button type="button" onClick={() => undefined} className="hover:underline bg-transparent border-0 p-0 cursor-pointer" style={{ color: 'var(--color-primary)' }}>
              Terms of Service
            </button>
            {' '}and{' '}
            <button type="button" onClick={() => undefined} className="hover:underline bg-transparent border-0 p-0 cursor-pointer" style={{ color: 'var(--color-primary)' }}>
              Privacy Policy
            </button>
          </p>
        </div>
      </div>
    </div>
  );
}

export default LoginPage;
