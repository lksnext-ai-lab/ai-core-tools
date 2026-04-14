import React, { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Bot,
  Database,
  Plug,
  Zap,
  Users,
  KeyRound,
} from 'lucide-react';
import { useDeploymentMode } from '../contexts/DeploymentModeContext';
import { useUser } from '../contexts/UserContext';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatLimit(n: number, unit: string): string {
  if (n === -1) return `Unlimited ${unit}`;
  return `${n} ${unit}`;
}

// ---------------------------------------------------------------------------
// Feature card data
// ---------------------------------------------------------------------------

const FEATURES = [
  {
    icon: <Bot size={28} />,
    title: 'Intelligent Agents',
    description:
      'Configure LLM agents with memory, system prompts, output parsers, and tool integrations.',
  },
  {
    icon: <Database size={28} />,
    title: 'Vector Knowledge Bases',
    description:
      'Silos with PGVector or Qdrant for RAG. Upload docs, crawl domains, query semantically.',
  },
  {
    icon: <Plug size={28} />,
    title: 'MCP Integration',
    description:
      'Connect agents to external tools via Model Context Protocol — Claude Desktop, Cursor, and more.',
  },
  {
    icon: <Zap size={28} />,
    title: 'Multi-Provider LLM',
    description:
      'OpenAI, Anthropic, Mistral, Azure, Google. Switch models without rewriting your agents.',
  },
  {
    icon: <Users size={28} />,
    title: 'Team Collaboration',
    description:
      'Invite collaborators with role-based access. Owners, administrators, editors, viewers.',
  },
  {
    icon: <KeyRound size={28} />,
    title: 'API & Marketplace',
    description:
      'Full REST API, public agent marketplace, and API key management for external access.',
  },
];

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function Navbar({ isLoggedIn, onDashboard }: { isLoggedIn: boolean; onDashboard: () => void }) {
  return (
    <nav className="sticky top-0 z-50 bg-white shadow-sm">
      <div className="max-w-7xl mx-auto px-6 py-3 flex items-center justify-between">
        {/* Logo */}
        <div className="flex items-center gap-2">
          <img src="/mattin-small.png" alt="Mattin AI logo" className="h-8 w-8 object-contain" />
          <span className="text-lg font-bold text-slate-900">Mattin AI</span>
        </div>

        {/* Nav actions */}
        <div className="flex items-center gap-3">
          {isLoggedIn ? (
            <button
              onClick={onDashboard}
              className="px-5 py-2 rounded-xl text-sm font-semibold text-white"
              style={{ backgroundColor: 'var(--color-primary)' }}
            >
              Go to Dashboard
            </button>
          ) : (
            <>
              <a
                href="/login"
                className="px-4 py-2 rounded-xl text-sm font-semibold border border-slate-300 text-slate-700 hover:bg-slate-50 transition-colors"
              >
                Log in
              </a>
              <a
                href="/register"
                className="px-4 py-2 rounded-xl text-sm font-semibold text-white transition-colors"
                style={{ backgroundColor: 'var(--color-primary)' }}
              >
                Get started free
              </a>
            </>
          )}
        </div>
      </div>
    </nav>
  );
}

function HeroSection({ isLoggedIn, onDashboard }: { isLoggedIn: boolean; onDashboard: () => void }) {
  return (
    <section
      className="relative overflow-hidden py-32 text-center"
      style={{ background: 'linear-gradient(135deg, #0f172a 0%, #1e3a5f 100%)' }}
    >
      {/* Animated background orbs */}
      <div className="absolute inset-0 pointer-events-none" aria-hidden="true">
        <div
          className="absolute top-1/4 left-1/4 w-96 h-96 rounded-full opacity-10 animate-pulse"
          style={{ backgroundColor: 'var(--color-primary)', filter: 'blur(80px)' }}
        />
        <div
          className="absolute bottom-1/4 right-1/4 w-64 h-64 rounded-full opacity-10 animate-pulse"
          style={{ backgroundColor: '#38bdf8', filter: 'blur(60px)', animationDelay: '1s' }}
        />
      </div>

      <div className="relative max-w-4xl mx-auto px-6">
        {/* Badge */}
        <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full border border-slate-600 text-slate-300 text-sm mb-8">
          <span style={{ color: 'var(--color-primary)' }}>✦</span>
          <span>AI Platform for Teams</span>
        </div>

        {/* Headline */}
        <h1 className="text-5xl sm:text-6xl font-bold text-white leading-tight mb-6">
          Build Your AI Workforce.
          <br />
          Deploy in Minutes.
        </h1>

        {/* Subheadline */}
        <p className="text-xl text-slate-300 max-w-2xl mx-auto mb-10">
          Mattin AI gives your team intelligent agents with RAG, vector search, and enterprise
          integrations — all in one platform.
        </p>

        {/* CTAs */}
        <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
          {isLoggedIn ? (
            <button
              onClick={onDashboard}
              className="px-8 py-4 rounded-xl text-lg font-semibold text-white transition-opacity hover:opacity-90"
              style={{ backgroundColor: 'var(--color-primary)' }}
            >
              Go to Dashboard →
            </button>
          ) : (
            <>
              <a
                href="/register"
                className="px-8 py-4 rounded-xl text-lg font-semibold text-white transition-opacity hover:opacity-90"
                style={{ backgroundColor: 'var(--color-primary)' }}
              >
                Start for free →
              </a>
              <a
                href="/login"
                className="px-8 py-4 rounded-xl text-lg font-semibold text-white border border-white/40 hover:bg-white/10 transition-colors"
              >
                Sign in
              </a>
            </>
          )}
        </div>
      </div>
    </section>
  );
}

function FeaturesSection() {
  return (
    <section className="bg-white py-24">
      <div className="max-w-6xl mx-auto px-6">
        <h2 className="text-3xl font-bold text-slate-900 text-center mb-16">
          Everything you need to build with AI
        </h2>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
          {FEATURES.map((feat) => (
            <div
              key={feat.title}
              className="p-6 rounded-2xl shadow-sm hover:shadow-md transition-shadow bg-white border border-slate-100"
            >
              <div className="mb-4" style={{ color: 'var(--color-primary)' }}>
                {feat.icon}
              </div>
              <h3 className="text-lg font-semibold text-slate-900 mb-2">{feat.title}</h3>
              <p className="text-slate-500 text-sm leading-relaxed">{feat.description}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

interface PricingCardProps {
  name: string;
  tagline: string;
  priceHint: string;
  limits: {
    apps: number;
    agents: number;
    silos: number;
    llm_calls: number;
    collaborators: number;
    mcp_servers: number;
  };
  note?: string;
  ctaLabel: string;
  ctaHref: string;
  highlighted?: boolean;
}

function PricingCard({
  name,
  tagline,
  priceHint,
  limits,
  note,
  ctaLabel,
  ctaHref,
  highlighted = false,
}: PricingCardProps) {
  const limitRows = [
    { label: 'Apps', value: formatLimit(limits.apps, 'apps') },
    { label: 'Agents per app', value: formatLimit(limits.agents, 'agents') },
    { label: 'Silos per app', value: formatLimit(limits.silos, 'silos') },
    { label: 'LLM calls / month', value: formatLimit(limits.llm_calls, 'calls') },
    { label: 'Collaborators', value: formatLimit(limits.collaborators, 'collaborators') },
    { label: 'MCP Servers', value: formatLimit(limits.mcp_servers, 'servers') },
  ];

  return (
    <div
      className={`flex flex-col rounded-2xl p-8 ${
        highlighted
          ? 'bg-white shadow-xl border-2'
          : 'bg-white shadow-sm border border-slate-200'
      }`}
      style={highlighted ? { borderColor: 'var(--color-primary)' } : undefined}
    >
      <div className="mb-6">
        <h3 className="text-xl font-bold text-slate-900 mb-1">{name}</h3>
        <p className="text-sm text-slate-500">{tagline}</p>
        <p
          className="mt-3 text-sm font-medium"
          style={{ color: 'var(--color-primary)' }}
        >
          {priceHint}
        </p>
      </div>

      <ul className="flex-1 space-y-3 mb-6">
        {limitRows.map((row) => (
          <li key={row.label} className="flex items-center justify-between text-sm">
            <span className="text-slate-600">{row.label}</span>
            <span className="font-medium text-slate-900">{row.value}</span>
          </li>
        ))}
      </ul>

      {note && (
        <p className="text-xs text-slate-400 mb-4 italic">{note}</p>
      )}

      <a
        href={ctaHref}
        className="block text-center py-3 rounded-xl font-semibold text-sm transition-opacity hover:opacity-90"
        style={
          highlighted
            ? { backgroundColor: 'var(--color-primary)', color: '#fff' }
            : { backgroundColor: '#f1f5f9', color: 'var(--color-primary)' }
        }
      >
        {ctaLabel}
      </a>
    </div>
  );
}

interface PricingSectionProps {
  tiers: {
    free: { apps: number; agents: number; silos: number; llm_calls: number; collaborators: number; mcp_servers: number };
    starter: { apps: number; agents: number; silos: number; llm_calls: number; collaborators: number; mcp_servers: number };
    pro: { apps: number; agents: number; silos: number; llm_calls: number; collaborators: number; mcp_servers: number };
  };
}

function PricingSection({ tiers }: PricingSectionProps) {
  return (
    <section className="bg-slate-50 py-24">
      <div className="max-w-5xl mx-auto px-6">
        <h2 className="text-3xl font-bold text-slate-900 text-center mb-3">
          Simple, transparent pricing
        </h2>
        <p className="text-center text-slate-500 mb-14">
          Start free, upgrade when you are ready
        </p>

        <div className="flex flex-col md:flex-row gap-6 items-stretch">
          <div className="flex-1">
            <PricingCard
              name="Free"
              tagline="Get started at no cost"
              priceHint="Free forever"
              limits={tiers.free}
              note="Use your own API keys for unlimited LLM usage"
              ctaLabel="Get started free"
              ctaHref="/register"
            />
          </div>
          <div className="flex-1">
            <PricingCard
              name="Starter"
              tagline="For growing teams"
              priceHint="For growing teams"
              limits={tiers.starter}
              ctaLabel="Get started"
              ctaHref="/register"
              highlighted
            />
          </div>
          <div className="flex-1">
            <PricingCard
              name="Pro"
              tagline="For power users"
              priceHint="For power users"
              limits={tiers.pro}
              note="Unlimited LLM calls via system AI services"
              ctaLabel="Get started"
              ctaHref="/register"
            />
          </div>
        </div>
      </div>
    </section>
  );
}

function CtaBanner() {
  return (
    <section
      className="py-20 text-center"
      style={{ background: 'linear-gradient(135deg, #0f172a 0%, #1e3a5f 100%)' }}
    >
      <div className="max-w-3xl mx-auto px-6">
        <h2 className="text-3xl font-bold text-white mb-4">
          Ready to build your AI workforce?
        </h2>
        <p className="text-slate-300 mb-10 text-lg">
          Join teams already using Mattin AI. Free to start, no credit card required.
        </p>
        <a
          href="/register"
          className="inline-block px-10 py-4 rounded-xl text-lg font-semibold bg-white transition-opacity hover:opacity-90"
          style={{ color: 'var(--color-primary)' }}
        >
          Create your free account →
        </a>
      </div>
    </section>
  );
}

function Footer() {
  return (
    <footer className="bg-slate-900 py-12">
      <div className="max-w-7xl mx-auto px-6">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-8">
          {/* Brand */}
          <div className="flex flex-col gap-2">
            <div className="flex items-center gap-2">
              <img
                src="/mattin-small.png"
                alt="Mattin AI logo"
                className="h-7 w-7 object-contain"
              />
              <span className="text-white font-bold text-base">Mattin AI</span>
            </div>
            <p className="text-slate-400 text-sm">
              The extensible AI toolbox for modern teams.
            </p>
          </div>

          {/* Links */}
          <div className="flex items-center gap-6 text-sm text-slate-400">
            <a href="/login" className="hover:text-white transition-colors">
              Log in
            </a>
            <a
              href="https://github.com/mattinai"
              target="_blank"
              rel="noopener noreferrer"
              className="hover:text-white transition-colors"
            >
              Documentation
            </a>
          </div>
        </div>

        <div className="mt-10 pt-6 border-t border-slate-800 text-center text-xs text-slate-500">
          &copy; {new Date().getFullYear()} Mattin AI. All rights reserved.
        </div>
      </div>
    </footer>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

const LandingPage: React.FC = () => {
  const { isSaasMode, isLoading, tiers } = useDeploymentMode();
  const { user } = useUser();
  const navigate = useNavigate();

  const isLoggedIn = Boolean(user?.is_authenticated);

  // In non-SaaS deployments, redirect straight to the app
  useEffect(() => {
    if (!isLoading && !isSaasMode) {
      navigate('/apps', { replace: true });
    }
  }, [isLoading, isSaasMode, navigate]);

  const handleDashboard = () => {
    navigate('/apps');
  };

  // Show nothing while deciding whether to redirect
  if (isLoading || !isSaasMode) {
    return null;
  }

  return (
    <div className="min-h-screen flex flex-col font-sans">
      <Navbar isLoggedIn={isLoggedIn} onDashboard={handleDashboard} />

      <main className="flex-1">
        <HeroSection isLoggedIn={isLoggedIn} onDashboard={handleDashboard} />
        <FeaturesSection />
        {tiers && <PricingSection tiers={tiers} />}
        <CtaBanner />
      </main>

      <Footer />
    </div>
  );
};

export default LandingPage;
