import React, { useState, useEffect, useCallback } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { apiService, type AgentRateLimitUsage } from '../services/api';
import {
  Bot,
  FolderOpen,
  Database,
  Globe,
  Settings,
  ChevronLeft,
  ArrowRight,
  Users,
  Zap,
  CheckCircle2,
  Circle,
  TrendingUp,
  Trophy,
  ChevronRight,
  X,
  Sparkles,
  Infinity as InfinityIcon,
  type LucideIcon,
} from 'lucide-react';
import Title from '../components/ui/Title';
import Alert from '../components/ui/Alert';
import { Badge } from '../components/ui/Badge';
import ButtonApp from '../components/ui/ButtonApp';
import ButtonLink from '../components/ui/ButtonLink';
import BackgroundImage from '../components/ui/BackgroundImage';
import { CardApp } from '../components/ui/CardApp';
import { LoadingState } from '../components/ui/LoadingState';
import { Skeleton } from '../components/ui/Skeleton';
import Speedometer from '../components/ui/Speedometer';
import { useTranslation } from 'react-i18next';

interface App {
  app_id: number;
  name: string;
  created_at: string;
  owner_id: number;
  owner_name?: string;
  owner_email?: string;
  role: string;
  langsmith_configured: boolean;
  agent_rate_limit: number;
  agent_count: number;
  repository_count: number;
  domain_count: number;
  silo_count: number;
  collaborator_count: number;
  onboarding_dismissed?: boolean;
}

interface Agent {
  agent_id: number;
  name: string;
  request_count: number;
}

interface FeatureCard {
  title: string;
  subtitle: string;
  count: number | null;
  icon: LucideIcon;
  href: string;
  label: string;
}

const EDITOR_ROLES = new Set(['owner', 'administrator', 'editor']);

function getUsageStressLevel(usage: AgentRateLimitUsage): 'low' | 'moderate' | 'high' | 'critical' {
  if (usage.is_over_limit || usage.usage_percentage >= 95) return 'critical';
  if (usage.usage_percentage >= 80) return 'high';
  if (usage.usage_percentage >= 50) return 'moderate';
  return 'low';
}

function AppDashboard() {
  const { appId } = useParams();
  const navigate = useNavigate();
  const { t } = useTranslation('common');

  const [currentApp, setCurrentApp] = useState<App | null>(null);
  const [loading, setLoading] = useState(true);

  const [agentUsageStats, setAgentUsageStats] = useState<AgentRateLimitUsage[] | null>(null);
  const [usageLoading, setUsageLoading] = useState(true);

  const [agents, setAgents] = useState<Agent[]>([]);
  const [agentsLoading, setAgentsLoading] = useState(true);

  const loadAppData = useCallback(async () => {
    if (!appId) return;
    try {
      setLoading(true);
      const app = await apiService.getApp(Number.parseInt(appId));
      setCurrentApp(app || null);
    } catch (error) {
      console.error('Failed to load app data:', error);
      setCurrentApp(null);
    } finally {
      setLoading(false);
    }
  }, [appId]);

  const loadAgentUsageStats = useCallback(async () => {
    if (!appId) return;
    try {
      setUsageLoading(true);
      const stats = await apiService.getAppAgentUsageStats(Number.parseInt(appId));
      setAgentUsageStats(stats);
    } catch (error) {
      console.error('Failed to load per-agent usage stats:', error);
      setAgentUsageStats(null);
    } finally {
      setUsageLoading(false);
    }
  }, [appId]);

  const loadAgents = useCallback(async () => {
    if (!appId) return;
    try {
      setAgentsLoading(true);
      const data = await apiService.getAgents(Number.parseInt(appId));
      setAgents(Array.isArray(data) ? data : []);
    } catch (error) {
      console.error('Failed to load agents:', error);
      setAgents([]);
    } finally {
      setAgentsLoading(false);
    }
  }, [appId]);

  const dismissChecklist = useCallback(async () => {
    if (!appId || !currentApp) return;
    try {
      await apiService.dismissOnboarding(Number.parseInt(appId));
      setCurrentApp(prev => prev ? { ...prev, onboarding_dismissed: true } : prev);
    } catch (error) {
      console.error('Failed to dismiss checklist:', error);
    }
  }, [appId, currentApp]);

  useEffect(() => {
    if (appId) {
      void loadAppData();
      void loadAgentUsageStats();
      void loadAgents();
    }
  }, [appId, loadAppData, loadAgentUsageStats, loadAgents]);

  if (loading) {
    return (
      <LoadingState variant="page" message={t('appDashboard.loadingWorkspace')} />
    );
  }

  if (!currentApp) {
    return (
      <Alert
        type="error"
        title={t('appDashboard.appNotFound')}
        message={(
          <>
            {t('appDashboard.requestedAppNotFound')}
            <Link to="/apps" className="mt-2 block underline">
              {t('appDashboard.backToApps')}
            </Link>
          </>
        )}
      />
    );
  }

  const cards: FeatureCard[] = [
    {
      title: t('appDashboard.features.agents.title'),
      subtitle: t('appDashboard.features.agents.subtitle'),
      count: currentApp.agent_count,
      icon: Bot,
      href: `/apps/${appId}/agents`,
      label: t('appDashboard.features.agents.action'),
    },
    {
      title: t('appDashboard.features.repositories.title'),
      subtitle: t('appDashboard.features.repositories.subtitle'),
      count: currentApp.repository_count,
      icon: FolderOpen,
      href: `/apps/${appId}/repositories`,
      label: t('appDashboard.features.repositories.action'),
    },
    {
      title: t('appDashboard.features.silos.title'),
      subtitle: t('appDashboard.features.silos.subtitle'),
      count: currentApp.silo_count,
      icon: Database,
      href: `/apps/${appId}/silos`,
      label: t('appDashboard.features.silos.action'),
    },
    {
      title: t('appDashboard.features.domains.title'),
      subtitle: t('appDashboard.features.domains.subtitle'),
      count: currentApp.domain_count,
      icon: Globe,
      href: `/apps/${appId}/domains`,
      label: t('appDashboard.features.domains.action'),
    },
    {
      title: t('appDashboard.features.settings.title'),
      subtitle: t('appDashboard.features.settings.subtitle'),
      count: null,
      icon: Settings,
      href: `/apps/${appId}/settings`,
      label: t('appDashboard.features.settings.action'),
    },
  ];

  // --- Hero badge helpers ---
  const rateLimitBadge = () => {
    if (currentApp.agent_rate_limit === 0) {
      return (
        <span className="inline-flex items-center gap-1 px-3 py-1 rounded-full text-xs font-medium bg-[var(--bg-sticky-verde)] text-[var(--text-sticky-verde)]">
          <InfinityIcon className="w-3 h-3" />
          {t('appDashboard.noLimit')}
        </span>
      );
    }
    if (!agentUsageStats) {
      return (
        <span className="inline-flex items-center gap-1 px-3 py-1 rounded-full text-xs font-medium bg-gray-100 text-gray-500">
          <Zap className="w-3 h-3" />
          {t('appDashboard.requestsPerMinute', { limit: currentApp.agent_rate_limit })}
        </span>
      );
    }
    return (
      <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium bg-gray-100 text-gray-500">
        <Zap className="w-3 h-3" />
        {currentApp.agent_rate_limit} req/min per agent
      </span>
    );
  };

  // --- Checklist logic ---
  const checklistSteps = [
    {
      label: t('appDashboard.checklist.createAgent'),
      done: currentApp.agent_count > 0,
      href: `/apps/${appId}/agents`,
    },
    {
      label: t('appDashboard.checklist.uploadDocuments'),
      done: currentApp.repository_count > 0,
      href: `/apps/${appId}/repositories`,
    },
    {
      label: t('appDashboard.checklist.createKnowledgeBase'),
      done: currentApp.silo_count > 0,
      href: `/apps/${appId}/silos`,
    },
    {
      label: t('appDashboard.checklist.addWebDomain'),
      done: currentApp.domain_count > 0,
      href: `/apps/${appId}/domains`,
    },
    {
      label: t('appDashboard.checklist.inviteCollaborator'),
      done: currentApp.collaborator_count > 1,
      href: `/apps/${appId}/settings`,
    },
  ];

  const completedCount = checklistSteps.filter((s) => s.done).length;
  const allComplete = completedCount === checklistSteps.length;
  const showChecklist = !currentApp.onboarding_dismissed && !allComplete;

  // --- Most-called agents ---
  const highestAgentUsage = [...(agentUsageStats ?? [])]
    .sort((a, b) => b.usage_percentage - a.usage_percentage)[0] ?? null;
  const highestUsageAgent = highestAgentUsage
    ? agents.find((agent) => agent.agent_id === highestAgentUsage.agent_id)
    : undefined;
  const rateLimitSummary = highestAgentUsage
    ? {
        usage_percentage: Math.max(0, Math.min(highestAgentUsage.usage_percentage, 100)),
        stress_level: getUsageStressLevel(highestAgentUsage),
        current_usage: highestAgentUsage.current_usage,
        limit: highestAgentUsage.limit,
        remaining: highestAgentUsage.remaining,
        reset_in_seconds: highestAgentUsage.reset_in_seconds,
        is_over_limit: highestAgentUsage.is_over_limit,
      }
    : null;
  const topAgents = [...agents]
    .sort((a, b) => (b.request_count ?? 0) - (a.request_count ?? 0))
    .slice(0, 5);
  const maxRequests = topAgents.reduce(
    (maximum, agent) => Math.max(maximum, agent.request_count ?? 0),
    0,
  );
  const canEdit = EDITOR_ROLES.has(currentApp.role);

  let rateLimitContent: React.ReactNode;
  if (currentApp.agent_rate_limit === 0) {
    rateLimitContent = (
      <div className="flex flex-col items-center justify-center py-6 gap-3">
        <BackgroundImage icon={InfinityIcon} size={64} iconSize={32} />        
        <p className="text-sm font-medium text-fg-secondary dark:text-fg-secondary-dark">
          {t('appDashboard.noLimitConfigured')}
        </p>
        <p className="text-center text-xs text-fg-secondary dark:text-fg-secondary-dark">
          {t('appDashboard.unlimitedRequestCapacity')}
        </p>
      </div>
    );
  } else if (usageLoading) {
    rateLimitContent = (
      <div className="flex flex-col items-center justify-center gap-3 py-6">
        <Skeleton shape="round" className="h-16 w-16" />
        <Skeleton className="h-3 w-24" />
        <Skeleton className="h-3 w-32" />
      </div>
    );
  } else if (!agentUsageStats || !rateLimitSummary) {
    rateLimitContent = (
      <p className="py-6 text-center text-xs text-fg-secondary dark:text-fg-secondary-dark">
        {t('appDashboard.usageDataUnavailable')}
      </p>
    );
  } else {
    rateLimitContent = (
      <div className="flex flex-col items-center gap-4">
        <Speedometer usageStats={rateLimitSummary} size="lg" showDetails />
        <div className="w-full border-t border-gray-100 pt-2">
          <p className="mb-2 text-center text-xs text-fg-secondary dark:text-fg-secondary-dark">
            {t('appDashboard.highestAgentUsage', {
              name: highestUsageAgent?.name ?? t('appDashboard.unknownAgent'),
            })}
          </p>
          <div className="flex justify-between gap-2 text-xs text-gray-500">
            <span>{t('appDashboard.limitRequestsPerMinute', { limit: rateLimitSummary.limit })}</span>
            <span>{t('appDashboard.remaining', { count: rateLimitSummary.remaining })}</span>
          </div>
        </div>
      </div>
    );
  }

  let agentsContent: React.ReactNode;
  if (agentsLoading) {
    agentsContent = (
      <div className="space-y-3">
        {[1, 2, 3].map((i) => (
          <div key={i} className="flex items-center gap-3">
            <Skeleton className="h-3 w-28" />
            <Skeleton shape="round" className="flex-1 h-2" />
            <Skeleton className="h-3 w-8" />
          </div>
        ))}
      </div>
    );
  } else if (topAgents.length === 0) {
    agentsContent = (
      <div className="flex flex-col items-center justify-center py-6 gap-3 text-center bg-btCard dark:bg-btCard-dark">
        <TrendingUp className="w-8 h-8 text-fg-secondary dark:text-fg-secondary-dark" />
        <p className="text-sm text-fg-secondary dark:text-fg-secondary-dark">{t('appDashboard.noAgentsYet')}</p>
        <Link
          to={`/apps/${appId}/agents`}
          className="text-xs text-fg-secondary dark:text-fg-secondary-dark font-medium flex items-center gap-0.5"
        >
          {t('appDashboard.createFirstAgent')}
          <ChevronRight className="w-3 h-3" />
        </Link>
      </div>
    );
  } else {
    agentsContent = (
      <>
        <div className="space-y-3">
          {topAgents.map((agent) => {
            const requestCount = agent.request_count ?? 0;
            const activityPercentage = maxRequests > 0
              ? Math.round((requestCount / maxRequests) * 100)
              : 0;
            return (
              <Link
                key={agent.agent_id}
                to={`/apps/${appId}/agents`}
                className="block group rounded-lg px-1 -mx-1 transition-colors"
                aria-label={`Go to ${agent.name}`}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="text-xs text-fg dark:text-fg-dark truncate" title={agent.name}>
                    {agent.name}
                  </span>
                  <span className="text-xs text-fg-secondary dark:text-fg-secondary-dark shrink-0">
                    {requestCount} total calls
                  </span>
                </div>
                <div
                  className="h-2 mt-1 bg-line dark:bg-line-dark rounded-full overflow-hidden"
                  aria-hidden="true"
                >
                  <div
                    className="h-full bg-accent dark:bg-fg-dark rounded-full transition-all duration-300"
                    style={{ width: `${activityPercentage}%` }}
                  />
                </div>
              </Link>
            );
          })}
        </div>
        {agents.length > topAgents.length && (
          <Link
            to={`/apps/${appId}/agents`}
            className="mt-3 inline-flex items-center gap-0.5 text-xs text-fg dark:text-fg-dark font-medium"
          >
            View all {agents.length} agents
            <ChevronRight className="w-3 h-3" />
          </Link>
        )}
      </>
    );
  }

  return (
    <div className="space-y-6">
      {/* ------------------------------------------------------------------ */}
      {/* Block 1: Enriched Hero Banner                                       */}
      {/* ------------------------------------------------------------------ */}
      <CardApp variant="canvas" className="p-6">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0 flex-1">
            <p className="text-xs text-bronze-dark uppercase tracking-wider mb-1">{t('appDashboard.workspace')}</p>
            <Title
              titulo={currentApp.name}
              subtitulo={t('appDashboard.subtitle')}
              variant="titTerciario"
              subtitleMarginBottom={0}
              titleMarginBottom={0}
            />
            {/* Info badges row */}
            <div className="flex flex-wrap items-center gap-2 mt-3">
              {/* Collaborators */}
              <span className="inline-flex items-center gap-1 rounded-full border border-color-border-card dark:border-btCard-border-dark bg-white dark:bg-canvas-alt-dark px-2.5 py-1 text-xs font-medium text-[var(--text-sticky-blanco)] dark:text-fg-secondary-dark">
                <Users className="w-3 h-3" />
                {t('appDashboard.collaborators', { count: currentApp.collaborator_count })}
              </span>

              {/* LangSmith */}
              <Badge
                label={currentApp.langsmith_configured
                  ? t('appDashboard.langSmithActive')
                  : t('appDashboard.langSmithNotConfigured')}
                variant={currentApp.langsmith_configured ? 'success' : 'default'}
                icon={(
                  <span
                    aria-hidden="true"
                    className={`h-2 w-2 rounded-full ${currentApp.langsmith_configured ? 'bg-success dark:bg-success-dark' : 'bg-fg-faint2 dark:bg-fg-faint2-dark'}`}
                  />
                )}
              />

              {/* Rate limit */}
              {rateLimitBadge()}
            </div>
          </div>

          {/* Action buttons */}
          <div className="flex items-center gap-2 shrink-0 flex-wrap justify-end">
            {canEdit && (
              <ButtonApp
                label={t('appDashboard.newAgent')}
                variant="primary"
                size="medium"
                icon={<Sparkles className="h-3.5 w-3.5" aria-hidden="true" />}
                onClick={() => navigate(`/apps/${appId}/agents`)}
              />
            )}
            <ButtonLink
              to="/apps"
              label={t('appDashboard.allApps')}
              variant="secondary"
              size="medium"
              icon={<ChevronLeft className="w-3.5 h-3.5" aria-hidden="true" />}
            />
          </div>
        </div>
      </CardApp>

      {/* ------------------------------------------------------------------ */}
      {/* Feature Cards (existing)                                            */}
      {/* ------------------------------------------------------------------ */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-4">
        {cards.map((card) => {
          return (
            <CardApp
              key={card.href}
              variant="white"
              className=""
            >
              {/* Icon + Count */}
              <div className="flex items-start justify-between mb-4">
                <BackgroundImage
                  icon={card.icon}
                  size={44}
                  variant="marron"
                  className="rounded-xl transition-all duration-200"
                />
                {card.count !== null && (
                  <div className="text-right">
                    <p className="text-2xl font-bold text-ink dark:dark:text-ink-dark">
                      {card.count}
                    </p>
                    <p className="text-xs text-fg-secondary dark:text-fg-secondary-dark leading-none">{t('appDashboard.total')}</p>
                  </div>
                )}
              </div>

              {/* Title + Subtitle */}
              <h3 className="font-semibold text-ink dark:dark:text-ink-dark text-sm mb-0.5">{card.title}</h3>
              <p className="text-fg-secondary dark:text-fg-secondary-dark text-xs mb-4 flex-1">{card.subtitle}</p>

              {/* CTA */}
              <Link
                to={card.href}
                className={`flex items-center text-sm font-medium text-bronze dark:text-bronze-dark transition-colors`}
              >
                {card.label}
                <ArrowRight className="w-3.5 h-3.5 ml-1 group-hover:translate-x-0.5 transition-transform duration-150" />
              </Link>
            </CardApp>
          );
        })}
      </div>

      {/* ------------------------------------------------------------------ */}
      {/* Per-agent call and rate-limit usage                                 */}
      {/* ------------------------------------------------------------------ */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <CardApp className="p-5" icon={Zap} titulo={t('appDashboard.rateLimitUsage')}>
            
          <p className="-mt-2 mb-3 text-xs text-fg-secondary dark:text-fg-secondary-dark">
            {t('appDashboard.rateLimitPeakDescription')}
          </p>
          {rateLimitContent}
        </CardApp>

        <CardApp className="p-5" icon={Trophy} titulo={t('appDashboard.topAgentsByUsage')}>
          <p className="text-xs text-fg-secondary dark:text-fg-secondary-dark -mt-2 mb-3">
            {t('appDashboard.topAgentsDescription')}
          </p>

          {agentsContent}
        </CardApp>
      </div>

      {/* ------------------------------------------------------------------ */}
      {/* Block 4: Getting Started Checklist                                  */}
      {/* ------------------------------------------------------------------ */}
      {showChecklist && (
        <CardApp
          className="p-5"
          icon={Sparkles}
          titulo={t('appDashboard.checklist.title')}
          headerExtra={canEdit && (
            <button
              onClick={() => void dismissChecklist()}
              className="text-gray-300 hover:text-gray-500 transition-colors rounded p-0.5"
              aria-label={t('appDashboard.checklist.dismiss')}
            >
              <X className="w-4 h-4" />
            </button>
          )}
        >
          <p className="-mt-2 mb-3 text-xs text-fg-secondary dark:text-fg-secondary-dark">
            {t('appDashboard.checklist.steps', { count: checklistSteps.length, completed: completedCount })}
          </p>

          {/* Progress bar */}
          <div className="w-full h-1.5 bg-line dark:bg-line-dark rounded-full mb-4 overflow-hidden">
            <div
              className="h-full bg-accent dark:bg-fg-dark rounded-full transition-all duration-500"
              style={{ width: `${(completedCount / checklistSteps.length) * 100}%` }}
            />
          </div>

          {/* Steps */}
          <div className="space-y-2">
            {checklistSteps.map((step) => {
              const row = (
                <>
                  {step.done ? (
                    <CheckCircle2 className="w-4 h-4 text-fg dark:text-fg-dark shrink-0" />
                  ) : (
                    <Circle className="w-4 h-4 text-fg-tertiary dark:text-fg-tertiary-dark shrink-0 transition-colors" />
                  )}
                  <span className={`text-sm flex-1 ${step.done ? 'text-fg dark:text-fg-dark line-through' : 'text-fg-tertiary dark:text-fg-tertiary-dark transition-colors'}`}>
                    {step.label}
                  </span>
                  {!step.done && (
                    <ChevronRight className="w-3.5 h-3.5 text-fg dark:text-fg-dark shrink-0" />
                  )}
                </>
              );

              return step.done ? (
                <div key={step.href} className="flex items-center gap-3">
                  {row}
                </div>
              ) : (
                <Link
                  key={step.href}
                  to={step.href}
                  className="flex items-center gap-3 group rounded-lg px-1 -mx-1  transition-colors"
                  aria-label={t('appDashboard.checklist.goToStep', { step: step.label })}
                >
                  {row}
                </Link>
              );
            })}
          </div>
        </CardApp>
      )}
    </div>
  );
}

export default AppDashboard;
