import React, { useState, useEffect, useCallback } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { apiService, type AgentRateLimitUsage } from '../services/api';
import {
  Bot,
  FolderOpen,
  Database,
  Globe,
  Settings,
  ArrowLeft,
  ArrowRight,
  AlertTriangle,
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
  gradient: string;
  iconColor: string;
  accentColor: string;
}

const EDITOR_ROLES = new Set(['owner', 'administrator', 'editor']);

function AppDashboard() {
  const { appId } = useParams();
  const navigate = useNavigate();

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
      <div className="flex items-center justify-center py-16">
        <div className="animate-spin rounded-full h-7 w-7 border-b-2 border-blue-600"></div>
        <span className="ml-3 text-gray-500 text-sm">Loading workspace...</span>
      </div>
    );
  }

  if (!currentApp) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-xl p-4">
        <div className="flex">
          <AlertTriangle className="w-5 h-5 text-red-400 mr-3 shrink-0 mt-0.5" />
          <div>
            <h3 className="text-sm font-medium text-red-800">App Not Found</h3>
            <p className="text-sm text-red-600 mt-1">The requested app could not be found.</p>
            <Link to="/apps" className="mt-2 inline-block text-sm text-red-600 hover:text-red-800 underline">
              Back to Apps
            </Link>
          </div>
        </div>
      </div>
    );
  }

  const cards: FeatureCard[] = [
    {
      title: 'AI Agents',
      subtitle: 'Intelligent automation',
      count: currentApp.agent_count,
      icon: Bot,
      href: `/apps/${appId}/agents`,
      label: 'Manage agents',
      gradient: 'from-blue-50 to-indigo-50',
      iconColor: 'text-blue-600',
      accentColor: 'text-blue-600 hover:text-blue-700',
    },
    {
      title: 'Repositories',
      subtitle: 'Document storage',
      count: currentApp.repository_count,
      icon: FolderOpen,
      href: `/apps/${appId}/repositories`,
      label: 'Manage repositories',
      gradient: 'from-emerald-50 to-teal-50',
      iconColor: 'text-emerald-600',
      accentColor: 'text-emerald-600 hover:text-emerald-700',
    },
    {
      title: 'Silos',
      subtitle: 'Vector knowledge bases',
      count: currentApp.silo_count,
      icon: Database,
      href: `/apps/${appId}/silos`,
      label: 'Manage silos',
      gradient: 'from-amber-50 to-yellow-50',
      iconColor: 'text-amber-600',
      accentColor: 'text-amber-600 hover:text-amber-700',
    },
    {
      title: 'Domains',
      subtitle: 'Web scraping sources',
      count: currentApp.domain_count,
      icon: Globe,
      href: `/apps/${appId}/domains`,
      label: 'Manage domains',
      gradient: 'from-violet-50 to-purple-50',
      iconColor: 'text-violet-600',
      accentColor: 'text-violet-600 hover:text-violet-700',
    },
    {
      title: 'App Settings',
      subtitle: 'Services & configuration',
      count: null,
      icon: Settings,
      href: `/apps/${appId}/settings`,
      label: 'Open settings',
      gradient: 'from-slate-50 to-gray-50',
      iconColor: 'text-slate-500',
      accentColor: 'text-slate-600 hover:text-slate-700',
    },
  ];

  // --- Hero badge helpers ---
  const rateLimitBadge = () => {
    if (currentApp.agent_rate_limit === 0) {
      return (
        <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium bg-green-100 text-green-700">
          <InfinityIcon className="w-3 h-3" />
          No limit
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
      label: 'Create an agent',
      done: currentApp.agent_count > 0,
      href: `/apps/${appId}/agents`,
    },
    {
      label: 'Upload documents',
      done: currentApp.repository_count > 0,
      href: `/apps/${appId}/repositories`,
    },
    {
      label: 'Create a knowledge base',
      done: currentApp.silo_count > 0,
      href: `/apps/${appId}/silos`,
    },
    {
      label: 'Add a web domain',
      done: currentApp.domain_count > 0,
      href: `/apps/${appId}/domains`,
    },
    {
      label: 'Invite a collaborator',
      done: currentApp.collaborator_count > 1,
      href: `/apps/${appId}/settings`,
    },
  ];

  const completedCount = checklistSteps.filter((s) => s.done).length;
  const allComplete = completedCount === checklistSteps.length;
  const showChecklist = !currentApp.onboarding_dismissed && !allComplete;

  // --- Most-called agents ---
  const agentUsageById = new Map(
    (agentUsageStats ?? []).map((usage) => [usage.agent_id, usage]),
  );
  const topAgents = [...agents]
    .sort((a, b) => (
      (b.request_count ?? 0) - (a.request_count ?? 0)
      || (agentUsageById.get(b.agent_id)?.current_usage ?? 0)
        - (agentUsageById.get(a.agent_id)?.current_usage ?? 0)
    ))
    .slice(0, 5);
  const hasCurrentAgentUsage = topAgents.some(
    (agent) => (agentUsageById.get(agent.agent_id)?.current_usage ?? 0) > 0,
  );

  const canEdit = EDITOR_ROLES.has(currentApp.role);

  let agentsContent: React.ReactNode;
  if (agentsLoading || usageLoading) {
    agentsContent = (
      <div className="space-y-3 animate-pulse">
        {[1, 2, 3].map((i) => (
          <div key={i} className="flex items-center gap-3">
            <div className="h-3 w-28 bg-gray-100 rounded" />
            <div className="flex-1 h-2 bg-gray-100 rounded-full" />
            <div className="h-3 w-8 bg-gray-100 rounded" />
          </div>
        ))}
      </div>
    );
  } else if (topAgents.length === 0) {
    agentsContent = (
      <div className="flex flex-col items-center justify-center py-6 gap-3 text-center">
        <TrendingUp className="w-8 h-8 text-gray-200" />
        <p className="text-sm text-gray-500">No agents yet.</p>
        <Link
          to={`/apps/${appId}/agents`}
          className="text-xs text-blue-600 hover:text-blue-700 font-medium flex items-center gap-0.5"
        >
          Create your first agent
          <ChevronRight className="w-3 h-3" />
        </Link>
      </div>
    );
  } else {
    agentsContent = (
      <>
        {agentUsageStats && currentApp.agent_rate_limit > 0 && !hasCurrentAgentUsage && (
          <p className="text-xs text-gray-400 dark:text-gray-500 mb-3">
            No requests in the current minute for these agents.
          </p>
        )}
        <div className="space-y-3">
          {topAgents.map((agent) => {
            const agentUsage = agentUsageById.get(agent.agent_id);
            const currentUsage = agentUsage?.current_usage ?? 0;
            const limit = currentApp.agent_rate_limit;
            const usagePercentage = Math.min(agentUsage?.usage_percentage ?? 0, 100);
            const remaining = agentUsage?.remaining ?? limit;
            const usageBarColor = usagePercentage >= 95
              ? 'bg-red-500'
              : usagePercentage >= 80
                ? 'bg-amber-500'
                : 'bg-blue-400';
            return (
              <Link
                key={agent.agent_id}
                to={`/apps/${appId}/agents`}
                className="block group rounded-lg px-1 -mx-1 hover:bg-blue-50 dark:hover:bg-gray-700 transition-colors"
                aria-label={`Go to ${agent.name}`}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="text-xs text-gray-700 dark:text-gray-200 truncate group-hover:text-blue-700 dark:group-hover:text-blue-300 transition-colors" title={agent.name}>
                    {agent.name}
                  </span>
                  <span className="text-xs text-gray-600 dark:text-gray-300 shrink-0">
                    {agent.request_count ?? 0} total calls
                  </span>
                </div>
                {limit > 0 && (
                  <>
                    <div className="flex items-center justify-between gap-2 mt-1.5 text-xs text-gray-500 dark:text-gray-400">
                      <span>Current minute</span>
                      <span>{currentUsage}/{limit} req/min</span>
                    </div>
                    <div
                      className="h-2 mt-1 bg-gray-100 dark:bg-gray-700 rounded-full overflow-hidden"
                      role="progressbar"
                      aria-label={`${agent.name} rate limit usage`}
                      aria-valuemin={0}
                      aria-valuemax={100}
                      aria-valuenow={usagePercentage}
                    >
                      <div
                        className={`h-full ${usageBarColor} rounded-full transition-all duration-300`}
                        style={{ width: `${usagePercentage}%` }}
                      />
                    </div>
                    <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">
                      {agentUsageStats
                        ? `${remaining} remaining${agentUsage ? ` · resets in ${agentUsage.reset_in_seconds}s` : ''}`
                        : 'Usage data unavailable'}
                    </p>
                  </>
                )}
                {limit === 0 && (
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-1.5">
                    No rate limit
                  </p>
                )}
              </Link>
            );
          })}
        </div>
        {agents.length > topAgents.length && (
          <Link
            to={`/apps/${appId}/agents`}
            className="mt-3 inline-flex items-center gap-0.5 text-xs text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300 font-medium"
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
      <div className="bg-gradient-to-r from-slate-50 via-blue-50 to-indigo-50 border border-slate-200 rounded-xl p-6">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0 flex-1">
            <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-1">Workspace</p>
            <h1 className="text-2xl font-bold text-gray-900 truncate">{currentApp.name}</h1>
            <p className="text-slate-500 text-sm mt-1">Manage your AI components and data resources</p>

            {/* Info badges row */}
            <div className="flex flex-wrap items-center gap-2 mt-3">
              {/* Collaborators */}
              <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium bg-slate-100 text-slate-600">
                <Users className="w-3 h-3" />
                {currentApp.collaborator_count} collaborator{currentApp.collaborator_count === 1 ? '' : 's'}
              </span>

              {/* LangSmith */}
              <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-slate-100 text-slate-600">
                <span
                  className={`w-2 h-2 rounded-full ${currentApp.langsmith_configured ? 'bg-green-500' : 'bg-gray-400'}`}
                />
                {currentApp.langsmith_configured ? 'LangSmith active' : 'LangSmith not configured'}
              </span>

              {/* Rate limit */}
              {rateLimitBadge()}
            </div>
          </div>

          {/* Action buttons */}
          <div className="flex items-center gap-2 shrink-0 flex-wrap justify-end">
            {canEdit && (
              <button
                onClick={() => navigate(`/apps/${appId}/agents`)}
                className="flex items-center gap-1.5 px-3 py-2 text-sm text-white bg-blue-600 hover:bg-blue-700 rounded-lg transition-colors font-medium"
              >
                <Sparkles className="w-3.5 h-3.5" />
                New Agent
              </button>
            )}
            <Link
              to="/apps"
              className="flex items-center gap-1.5 px-3 py-2 text-sm text-slate-600 hover:text-slate-900 bg-white hover:bg-slate-50 rounded-lg border border-slate-200 transition-colors"
            >
              <ArrowLeft className="w-3.5 h-3.5" />
              All Apps
            </Link>
          </div>
        </div>
      </div>

      {/* ------------------------------------------------------------------ */}
      {/* Feature Cards (existing)                                            */}
      {/* ------------------------------------------------------------------ */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-4">
        {cards.map((card) => {
          const Icon = card.icon;
          return (
            <div
              key={card.href}
              className="bg-white rounded-xl border border-gray-200 p-5 hover:shadow-md hover:border-gray-300 transition-all duration-200 group flex flex-col"
            >
              {/* Icon + Count */}
              <div className="flex items-start justify-between mb-4">
                <div className={`w-11 h-11 bg-gradient-to-br ${card.gradient} rounded-xl flex items-center justify-center transition-all duration-200`}>
                  <Icon className={`w-5 h-5 ${card.iconColor}`} />
                </div>
                {card.count !== null && (
                  <div className="text-right">
                    <p className={`text-2xl font-bold ${card.count > 0 ? 'text-gray-900' : 'text-gray-300'}`}>
                      {card.count}
                    </p>
                    <p className="text-xs text-gray-400 leading-none">total</p>
                  </div>
                )}
              </div>

              {/* Title + Subtitle */}
              <h3 className="font-semibold text-gray-900 text-sm mb-0.5">{card.title}</h3>
              <p className="text-gray-400 text-xs mb-4 flex-1">{card.subtitle}</p>

              {/* CTA */}
              <Link
                to={card.href}
                className={`flex items-center text-sm font-medium ${card.accentColor} transition-colors`}
              >
                {card.label}
                <ArrowRight className="w-3.5 h-3.5 ml-1 group-hover:translate-x-0.5 transition-transform duration-150" />
              </Link>
            </div>
          );
        })}
      </div>

      {/* ------------------------------------------------------------------ */}
      {/* Per-agent call and rate-limit usage                                 */}
      {/* ------------------------------------------------------------------ */}
      <div className="grid grid-cols-1 gap-4">
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
          <div className="flex items-center gap-2 mb-4">
            <Trophy className="w-4 h-4 text-blue-500" />
            <h2 className="text-sm font-semibold text-gray-800 dark:text-gray-100">Most Called Agents</h2>
          </div>
          <p className="text-xs text-gray-500 dark:text-gray-400 -mt-2 mb-3">
            Total calls and current-minute rate-limit usage.
          </p>

          {agentsContent}
        </div>
      </div>

      {/* ------------------------------------------------------------------ */}
      {/* Block 4: Getting Started Checklist                                  */}
      {/* ------------------------------------------------------------------ */}
      {showChecklist && (
        <div className="bg-white rounded-xl border border-gray-200 p-5">
          {/* Header row */}
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-indigo-500" />
              <h2 className="text-sm font-semibold text-gray-800">Getting Started</h2>
              <span className="text-xs text-gray-400 font-normal">
                {completedCount} / {checklistSteps.length} steps
              </span>
            </div>
            {canEdit && (
              <button
                onClick={() => void dismissChecklist()}
                className="text-gray-300 hover:text-gray-500 transition-colors rounded p-0.5"
                aria-label="Dismiss checklist"
              >
                <X className="w-4 h-4" />
              </button>
            )}
          </div>

          {/* Progress bar */}
          <div className="w-full h-1.5 bg-gray-100 rounded-full mb-4 overflow-hidden">
            <div
              className="h-full bg-indigo-500 rounded-full transition-all duration-500"
              style={{ width: `${(completedCount / checklistSteps.length) * 100}%` }}
            />
          </div>

          {/* Steps */}
          <div className="space-y-2">
            {checklistSteps.map((step) => {
              const row = (
                <>
                  {step.done ? (
                    <CheckCircle2 className="w-4 h-4 text-green-500 shrink-0" />
                  ) : (
                    <Circle className="w-4 h-4 text-gray-300 shrink-0 group-hover:text-indigo-400 transition-colors" />
                  )}
                  <span className={`text-sm flex-1 ${step.done ? 'text-gray-400 line-through' : 'text-gray-700 group-hover:text-indigo-700 transition-colors'}`}>
                    {step.label}
                  </span>
                  {!step.done && (
                    <ChevronRight className="w-3.5 h-3.5 text-gray-300 group-hover:text-indigo-500 transition-colors shrink-0" />
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
                  className="flex items-center gap-3 group rounded-lg px-1 -mx-1 hover:bg-indigo-50 transition-colors"
                  aria-label={`Go to ${step.label}`}
                >
                  {row}
                </Link>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

export default AppDashboard;
