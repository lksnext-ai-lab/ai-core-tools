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
import { useTranslation } from 'react-i18next';
import { ButtonApp } from '../components/ui/ButtonApp';
import { ButtonLink } from '../components/ui/ButtonLink';
import CardApp from '../components/ui/CardApp';
import { useDeploymentMode } from '../contexts/DeploymentModeContext';
import { useUser } from '../contexts/UserContext';

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function Navbar({ isLoggedIn, onDashboard }: { isLoggedIn: boolean; onDashboard: () => void }) {
  const { t } = useTranslation('common');

  return (
    <nav className="sticky top-0 z-50 border-b border-line bg-surface dark:border-line-dark dark:bg-surface-dark">
      <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-3 sm:px-6 lg:px-10">
        {/* Logo */}
        <div className="flex items-center gap-2">
          <img src="/mattin-small.png" alt={t('landingPage.logoAlt')} className="h-8 w-8 object-contain" />
          <span className="font-display text-lg font-medium text-ink dark:text-ink-dark">Mattin AI</span>
        </div>

        {/* Nav actions */}
        <div className="flex items-center gap-3">
          {isLoggedIn ? (
            <ButtonApp
              label={t('landingPage.goToDashboard')}
              onClick={onDashboard}
              variant="primary"
              size="medium"
            />
          ) : (
            <>
              <ButtonLink label={t('landingPage.logIn')} to="/login" variant="secondary" size="medium" />
              <ButtonLink label={t('landingPage.getStartedFree')} to="/register" variant="primary" size="medium" />
            </>
          )}
        </div>
      </div>
    </nav>
  );
}

function HeroSection({ isLoggedIn, onDashboard }: { isLoggedIn: boolean; onDashboard: () => void }) {
  const { t } = useTranslation('common');

  return (
    <section className="border-b border-line bg-canvas-alt py-16 dark:border-line-dark dark:bg-canvas-alt-dark sm:py-24">
      <div className="mx-auto max-w-5xl px-4 text-center sm:px-6">
        {/* Badge */}
        <div className="mb-6 inline-flex items-center gap-2 rounded-md border border-bronze-border bg-bronze-bg px-3 py-1.5 text-sm text-bronze dark:border-bronze-border-dark dark:bg-bronze-bg-dark dark:text-bronze-dark">
          <span aria-hidden="true">✦</span>
          <span>{t('landingPage.heroBadge')}</span>
        </div>

        {/* Headline */}
        <h1 className="font-display text-4xl font-medium leading-tight tracking-[-0.03em] text-ink dark:text-ink-dark sm:text-5xl">
          {t('landingPage.heroHeadlineFirst')}
          <br />
          {t('landingPage.heroHeadlineSecond')}
        </h1>

        {/* Subheadline */}
        <p className="mx-auto mt-6 max-w-2xl text-base leading-7 text-fg-secondary dark:text-fg-secondary-dark sm:text-lg">
          {t('landingPage.heroDescription')}
        </p>

        {/* CTAs */}
        <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
          {isLoggedIn ? (
            <ButtonApp
              label={`${t('landingPage.goToDashboard')} →`}
              onClick={onDashboard}
              variant="primary"
              size="large"
            />
          ) : (
            <>
              <ButtonLink
                label={`${t('landingPage.startForFree')} →`}
                to="/register"
                variant="primary"
                size="large"
              />
              <ButtonLink label={t('landingPage.signIn')} to="/login" variant="secondary" size="large" />
            </>
          )}
        </div>
      </div>
    </section>
  );
}

function FeaturesSection() {
  const { t } = useTranslation('common');
  const features = [
    {
      icon: Bot,
      title: t('landingPage.features.agentsTitle'),
      description: t('landingPage.features.agentsDescription'),
    },
    {
      icon: Database,
      title: t('landingPage.features.knowledgeTitle'),
      description: t('landingPage.features.knowledgeDescription'),
    },
    {
      icon: Plug,
      title: t('landingPage.features.mcpTitle'),
      description: t('landingPage.features.mcpDescription'),
    },
    {
      icon: Zap,
      title: t('landingPage.features.llmTitle'),
      description: t('landingPage.features.llmDescription'),
    },
    {
      icon: Users,
      title: t('landingPage.features.collaborationTitle'),
      description: t('landingPage.features.collaborationDescription'),
    },
    {
      icon: KeyRound,
      title: t('landingPage.features.apiTitle'),
      description: t('landingPage.features.apiDescription'),
    },
  ];

  return (
    <section className="bg-canvas py-16 dark:bg-canvas-dark sm:py-20">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-10">
        <h2 className="mb-10 text-center font-display text-3xl font-medium text-ink dark:text-ink-dark sm:mb-12">
          {t('landingPage.features.title')}
        </h2>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {features.map((feature) => (
            <CardApp
              variant="canvas"
              icon={feature.icon}
              titulo={feature.title}
              key={feature.title}
              className="gap-2"
            >
              <p className="text-sm leading-6 text-fg-secondary dark:text-fg-secondary-dark">
                {feature.description}
              </p>
            </CardApp>
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
  const { t } = useTranslation('common');
  const formatLimit = (
    n: number,
    unit: 'apps' | 'agents' | 'silos' | 'llmCalls' | 'collaborators' | 'servers',
  ) => {
    const unitLabel = t(`landingPage.units.${unit}`, { count: n === -1 ? 2 : n });
    return n === -1
      ? t('landingPage.unlimited', { unit: unitLabel })
      : `${n} ${unitLabel}`;
  };
  const limitRows = [
    { label: t('landingPage.pricing.apps'), value: formatLimit(limits.apps, 'apps') },
    { label: t('landingPage.pricing.agentsPerApp'), value: formatLimit(limits.agents, 'agents') },
    { label: t('landingPage.pricing.silosPerApp'), value: formatLimit(limits.silos, 'silos') },
    { label: t('landingPage.pricing.llmCallsPerMonth'), value: formatLimit(limits.llm_calls, 'llmCalls') },
    { label: t('landingPage.pricing.collaborators'), value: formatLimit(limits.collaborators, 'collaborators') },
    { label: t('landingPage.pricing.mcpServers'), value: formatLimit(limits.mcp_servers, 'servers') },
  ];

  return (
    <CardApp variant={highlighted ? 'canvas' : 'white'} titulo={name} subtitulo={tagline} className="gap-5">
      <div>
        <p className="text-sm font-medium text-bronze dark:text-bronze-dark">
          {priceHint}
        </p>
      </div>

      <ul className="flex-1 divide-y divide-line dark:divide-line-dark">
        {limitRows.map((row) => (
          <li key={row.label} className="flex items-center justify-between gap-3 py-3 text-sm">
            <span className="text-fg-secondary dark:text-fg-secondary-dark">{row.label}</span>
            <span className="text-right font-medium text-fg dark:text-fg-dark">{row.value}</span>
          </li>
        ))}
      </ul>

      {note && <p className="text-xs leading-5 text-fg-tertiary dark:text-fg-tertiary-dark">{note}</p>}

      <ButtonLink
        label={ctaLabel}
        to={ctaHref}
        variant={highlighted ? 'primary' : 'secondary'}
        size="medium"
        className="w-full"
      />
    </CardApp>
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
  const { t } = useTranslation('common');

  return (
    <section className="bg-canvas-alt py-16 dark:bg-canvas-alt-dark sm:py-20">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-10">
        <h2 className="text-center font-display text-3xl font-medium text-ink dark:text-ink-dark">
          {t('landingPage.pricing.title')}
        </h2>
        <p className="mb-8 mt-2 text-center text-sm text-fg-secondary dark:text-fg-secondary-dark sm:mb-10">
          {t('landingPage.pricing.subtitle')}
        </p>

        <div className="grid grid-cols-1 items-stretch gap-4 md:grid-cols-3">
          <PricingCard
            name={t('landingPage.pricing.free')}
            tagline={t('landingPage.pricing.freeTagline')}
            priceHint={t('landingPage.pricing.freePriceHint')}
            limits={tiers.free}
            note={t('landingPage.pricing.freeNote')}
            ctaLabel={t('landingPage.getStartedFree')}
            ctaHref="/register"
          />
          <PricingCard
            name={t('landingPage.pricing.starter')}
            tagline={t('landingPage.pricing.starterTagline')}
            priceHint={t('landingPage.pricing.starterPriceHint')}
            limits={tiers.starter}
            ctaLabel={t('landingPage.pricing.getStarted')}
            ctaHref="/register"
            highlighted
          />
          <PricingCard
            name={t('landingPage.pricing.pro')}
            tagline={t('landingPage.pricing.proTagline')}
            priceHint={t('landingPage.pricing.proPriceHint')}
            limits={tiers.pro}
            note={t('landingPage.pricing.proNote')}
            ctaLabel={t('landingPage.pricing.getStarted')}
            ctaHref="/register"
          />
        </div>
      </div>
    </section>
  );
}

function CtaBanner() {
  const { t } = useTranslation('common');

  return (
    <section className="bg-canvas py-16 dark:bg-canvas-dark sm:py-20">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-10">
        <CardApp variant="canvas" className="items-center gap-5 p-8 text-center sm:p-12">
          <h2 className="font-display text-3xl font-medium text-ink dark:text-ink-dark">
          {t('landingPage.ctaTitle')}
          </h2>
          <p className="max-w-2xl text-base leading-7 text-fg-secondary dark:text-fg-secondary-dark">
            {t('landingPage.ctaDescription')}
          </p>
          <ButtonLink
            label={`${t('landingPage.createFreeAccount')} →`}
            to="/register"
            variant="primary"
            size="large"
          />
        </CardApp>
      </div>
    </section>
  );
}

function Footer() {
  const { t } = useTranslation('common');

  return (
    <footer className="border-t border-line bg-surface dark:border-line-dark dark:bg-surface-dark">
      <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-10">
        <div className="flex flex-col items-start justify-between gap-6 sm:flex-row sm:items-center">
          {/* Brand */}
          <div className="flex flex-col gap-2">
            <div className="flex items-center gap-2">
              <img
                src="/mattin-small.png"
                alt={t('landingPage.logoAlt')}
                className="h-7 w-7 object-contain"
              />
              <span className="font-display text-base font-medium text-ink dark:text-ink-dark">Mattin AI</span>
            </div>
            <p className="text-sm text-fg-secondary dark:text-fg-secondary-dark">
              {t('landingPage.footerTagline')}
            </p>
          </div>

          {/* Links */}
          <div className="flex items-center gap-6 text-sm text-fg-secondary dark:text-fg-secondary-dark">
            <a href="/login" className="transition-colors hover:text-accent dark:hover:text-accent-dark">
              {t('landingPage.logIn')}
            </a>
            <a
              href="https://github.com/mattinai"
              target="_blank"
              rel="noopener noreferrer"
              className="transition-colors hover:text-accent dark:hover:text-accent-dark"
            >
              {t('landingPage.documentation')}
            </a>
          </div>
        </div>

        <div className="mt-6 border-t border-line pt-5 text-center text-xs text-fg-tertiary dark:border-line-dark dark:text-fg-tertiary-dark">
          {t('landingPage.copyright', { year: new Date().getFullYear() })}
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
    <div className="flex min-h-screen flex-col bg-canvas font-sans text-fg dark:bg-canvas-dark dark:text-fg-dark">
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
