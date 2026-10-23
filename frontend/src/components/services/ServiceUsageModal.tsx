import { useEffect, useId, useMemo, useRef, useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import Modal from '../ui/Modal';
import ServiceStatusBadge from '../ui/ServiceStatusBadge';
import { apiService, ApiError } from '../../services/api';
import type { ServiceUsage } from '../../types/services';
import { ButtonApp } from '../ui/ButtonApp';
import { FormSelect } from '../ui/FormField';
import Alert from '../ui/Alert';
import {
  SERVICE_LIFECYCLE_STRINGS,
  SERVICE_USAGE_STRINGS as S,
  formatEndOfServiceDate,
  type ServiceOptionLike,
} from '../../utils/serviceLifecycle';
import CardApp from '../ui/CardApp';

const PANEL_CARD =
  'rounded-xl border border-line dark:border-line-dark bg-surface dark:bg-surface-dark p-6 mt-2';
const PANEL_CARD_TITLE =
  'font-display text-[17px] font-medium text-fg dark:text-fg-dark mb-3';

export interface ServiceUsageModalProps {
  readonly onClose: () => void;
  readonly kind: 'ai' | 'embedding' | 'sandbox';
  /** `app`: app-scoped endpoints. `system`: platform-admin cross-app endpoints (shows app names). */
  readonly scope: 'app' | 'system';
  /** Required when scope is `app`. */
  readonly appId?: number;
  readonly serviceId: number;
  readonly serviceName: string;
  /** App scope + AI or sandbox service only: user is ADMINISTRATOR or higher. */
  readonly canMove?: boolean;
  /** Called after agents were moved so the parent can refresh its list. */
  readonly onMoved?: () => void;
  /** Enables a delete action after the service usage has been reviewed. */
  readonly onDelete?: () => Promise<boolean>;
  /** Entries link to editor-only pages; false renders them as plain text (VIEWER). */
  readonly canNavigate?: boolean;
  /** `panel`: renders only the content, to be placed inside a SidePanel by the parent. */
  readonly variant?: 'modal' | 'panel';
}

interface SectionProps {
  readonly title: string;
  readonly count: number;
  readonly children: ReactNode;
}

function Section({ title, count, children }: SectionProps) {
  const headingId = useId();
  return (
    <CardApp className={PANEL_CARD}>
      <h4 id={headingId} className={PANEL_CARD_TITLE}>
        {title} ({count})
      </h4>
      {count === 0 ? (
        <p className="text-sm text-fg-secondary dark:text-fg-secondary-dark">{S.empty}</p>
      ) : (
        <ul className="space-y-3">
          {children}
        </ul>
      )}
    </CardApp>
  );
}

interface EntryProps {
  readonly to: string;
  readonly name: string;
  readonly detail?: string;
  readonly appName?: string | null;
  readonly canNavigate: boolean;
}

function Entry({ to, name, detail, appName, canNavigate }: EntryProps) {
  const descId = useId();
  const hasDesc = Boolean(detail || appName);
  return (
    <li className="relative p-3 rounded-lg border border-line dark:border-line-dark hover:bg-surface-hover dark:hover:bg-surface-hover-dark transition-colors">
      {canNavigate ? (
        <Link
          to={to}
          aria-describedby={hasDesc ? descId : undefined}
          className="block text-sm font-medium text-fg dark:text-fg-dark truncate focus:outline-none after:absolute after:inset-0 after:rounded-lg after:content-['']"
        >
          {name}
        </Link>
      ) : (
        <span className="block text-sm font-medium text-fg dark:text-fg-dark truncate">{name}</span>
      )}
      {hasDesc && (
        <span id={descId} className="block mt-1 text-xs text-fg-faint dark:text-fg-faint-dark truncate">
          {detail}
          {detail && appName ? ' · ' : ''}
          {appName && S.appLabel(appName)}
        </span>
      )}
    </li>
  );
}

function ServiceUsageModal({
  onClose,
  kind,
  scope,
  appId,
  serviceId,
  serviceName,
  canMove = false,
  onMoved,
  onDelete,
  canNavigate = true,
  variant = 'modal',
}: ServiceUsageModalProps) {
  const isPanel = variant === 'panel';
  const showMove = canMove && (kind === 'ai' || kind === 'sandbox') && scope === 'app' && appId !== undefined;

  const [usage, setUsage] = useState<ServiceUsage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  const [targets, setTargets] = useState<readonly ServiceOptionLike[]>([]);
  const [targetsLoading, setTargetsLoading] = useState(showMove);
  const [targetsError, setTargetsError] = useState<string | null>(null);
  const [targetsReloadKey, setTargetsReloadKey] = useState(0);
  const [targetId, setTargetId] = useState('');
  const [confirming, setConfirming] = useState(false);
  const [moving, setMoving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [moveMessage, setMoveMessage] = useState<{ text: string; type: 'success' | 'error' } | null>(null);
  const selectId = useId();
  const confirmTextId = useId();
  const moveBtnRef = useRef<HTMLButtonElement>(null);
  const cancelBtnRef = useRef<HTMLButtonElement>(null);
  const messageRef = useRef<HTMLDivElement>(null);
  const loadStatusRef = useRef<HTMLParagraphElement>(null);
  const moveHeadingRef = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    let request: Promise<ServiceUsage>;
    if (scope === 'system') {
      if (kind === 'ai') request = apiService.getSystemAIServiceUsedBy(serviceId);
      else if (kind === 'sandbox') request = apiService.getSystemSandboxServiceUsedBy(serviceId);
      else request = apiService.getSystemEmbeddingServiceUsedBy(serviceId);
    } else if (appId === undefined) {
      request = Promise.reject(new Error(S.loadError));
    } else {
      if (kind === 'ai') request = apiService.getAIServiceUsedBy(appId, serviceId);
      else if (kind === 'sandbox') request = apiService.getSandboxServiceUsedBy(appId, serviceId);
      else request = apiService.getEmbeddingServiceUsedBy(appId, serviceId);
    }
    request
      .then((data) => {
        if (!cancelled) setUsage(data);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error && err.message ? err.message : S.loadError);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [kind, scope, appId, serviceId, reloadKey]);

  useEffect(() => {
    if (!showMove || appId === undefined) return;
    let cancelled = false;
    setTargetsLoading(true);
    setTargetsError(null);
    setTargets([]);
    const request = kind === 'ai'
      ? apiService.getAIServices(appId)
      : apiService.getSandboxServices(appId);
    request
      .then((list) => {
        if (!cancelled) setTargets(list as readonly ServiceOptionLike[]);
      }).catch((err: unknown) => {
        if (!cancelled) {
          setTargetsError(err instanceof Error && err.message ? err.message : S.targetsLoadError);
        }
      }).finally(() => {
        if (!cancelled) setTargetsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [showMove, kind, appId, reloadKey, targetsReloadKey]);

  useEffect(() => {
    if (confirming) cancelBtnRef.current?.focus();
  }, [confirming]);

  useEffect(() => {
    if (moveMessage) messageRef.current?.focus();
  }, [moveMessage]);

  function cancelConfirm() {
    setConfirming(false);
    // Wait for the re-render that re-enables the Move button before focusing it.
    requestAnimationFrame(() => moveBtnRef.current?.focus());
  }

  const targetOptions = useMemo(
    () => targets.filter((t) => t.service_id !== serviceId && t.lifecycle_status !== 'retired'),
    [targets, serviceId],
  );
  const moveAgentCount = useMemo(
    () => (usage
      ? usage.agents.filter((a) => a.roles.includes(kind === 'ai' ? 'llm' : 'sandbox')).length
      : 0),
    [usage, kind],
  );
  const moveAppCount = kind === 'sandbox' ? usage?.apps_using_as_default?.length ?? 0 : 0;
  const moveInheritedCount = useMemo(
    () => (usage && kind === 'sandbox'
      ? usage.agents.filter((a) => a.roles.includes('sandbox_app_default')).length
      : 0),
    [usage, kind],
  );
  const moveUsageCount = moveAgentCount + moveAppCount;
  const selectedTarget = targetOptions.find((t) => String(t.service_id) === targetId) ?? null;

  function optionLabel(t: ServiceOptionLike): string {
    return t.lifecycle_status === 'deprecated' && t.end_of_service_at
      ? S.moveTargetEnds(t.name, formatEndOfServiceDate(t.end_of_service_at))
      : t.name;
  }

  async function handleMove() {
    if (appId === undefined || !selectedTarget) return;
    setMoving(true);
    setMoveMessage(null);
    try {
      if (kind === 'ai') {
        const result = await apiService.moveAgentsToAIService(
          appId,
          serviceId,
          selectedTarget.service_id,
          moveAgentCount,
        );
        setMoveMessage({ text: S.moveSuccess(result.count), type: 'success' });
      } else {
        const result = await apiService.moveSandboxServiceUsage(
          appId,
          serviceId,
          selectedTarget.service_id,
          moveAgentCount,
          moveAppCount,
        );
        setMoveMessage({
          text: S.moveSandboxSuccess(result.moved_agent_ids.length, result.updated_app_ids.length),
          type: 'success',
        });
      }
      setConfirming(false);
      setTargetId('');
      setReloadKey((k) => k + 1);
      onMoved?.();
    } catch (err: unknown) {
      setConfirming(false);
      setMoveMessage({
        text: err instanceof Error && err.message ? err.message : S.moveError,
        type: 'error',
      });
      // Count changed (409): reload the usage so the user sees the new number before confirming again.
      if (err instanceof ApiError && err.status === 409) setReloadKey((k) => k + 1);
    } finally {
      setMoving(false);
    }
  }

  async function handleDelete() {
    if (!onDelete) return;
    setDeleting(true);
    try {
      const deleted = await onDelete();
      if (deleted) onClose();
    } finally {
      setDeleting(false);
    }
  }

  const base = (id: number) => `/apps/${id}`;
  const scopedApp = (name?: string | null) => (scope === 'system' ? name : null);

  function renderMove(u: ServiceUsage) {
    if (!showMove) return null;
    const isAI = kind === 'ai';
    return (
      <section
        aria-labelledby={`${selectId}-move`}
        className="mt-6 border-t border-gray-200 dark:border-slate-600 pt-4"
      >
        <h4 ref={moveHeadingRef} tabIndex={-1} id={`${selectId}-move`} className="text-sm font-semibold text-fg dark:text-fg-dark mb-1">
          {isAI ? S.moveTitle : S.moveSandboxTitle}
        </h4>
        <p className="text-sm text-fg-secondary dark:text-fg-secondary-dark mb-3">
          {isAI
            ? (moveAgentCount > 0 ? S.moveCount(moveAgentCount) : S.moveNone)
            : S.moveSandboxSummary(moveAgentCount, moveAppCount)}
        </p>
        {moveUsageCount > 0 && targetsLoading && (
          <p role="status" className="text-sm text-fg-secondary dark:text-fg-secondary-dark mb-3">
            {S.targetsLoading}
          </p>
        )}
        {moveUsageCount > 0 && targetsError && (
          <Alert
            type="error"
            className="mb-3"
            message={(
              <>
                <p>{targetsError}</p>
                <button
                  type="button"
                  onClick={() => {
                    setTargetsReloadKey((key) => key + 1);
                    moveHeadingRef.current?.focus();
                  }}
                  className="mt-2 underline focus:outline-none focus:ring-2 focus:ring-red-500 rounded"
                >
                  {S.retry}
                </button>
              </>
            )}
          />
        )}
        {moveUsageCount > 0 && !targetsLoading && !targetsError && targetOptions.length === 0 && (
          <p className="text-sm text-fg-secondary dark:text-fg-secondary-dark mb-3">
            {isAI ? S.moveNoTargets : S.moveSandboxNoTargets}
          </p>
        )}
        {moveUsageCount > 0 && !targetsLoading && !targetsError && targetOptions.length > 0 && (
          <div className="space-y-3">
            <FormSelect
              id={selectId}
              label={isAI ? S.moveTargetLabel : S.moveSandboxTargetLabel}
              value={targetId}
              disabled={moving}
              onChange={(e) => {
                setTargetId(e.target.value);
                setConfirming(false);
              }}
              options={[
                { value: '', label: S.moveTargetPlaceholder },
                ...targetOptions.map((t) => ({ value: t.service_id, label: optionLabel(t) })),
              ]}
            />
            <ButtonApp
              ref={moveBtnRef}
              label={isAI ? S.moveButton : S.moveSandboxButton}
              type="button"
              disabled={!selectedTarget || confirming}
              onClick={() => setConfirming(true)}
              variant="primary"
              size="medium"
            />
           {confirming && selectedTarget && (
              <div
                role="group"
                aria-labelledby={confirmTextId}
                className="rounded-lg border border-bronze-strong bg-bronze-bg-soft dark:border-bronze-strong-dark dark:bg-bronze-bg-soft p-3"
              >
                <p id={confirmTextId} className="text-sm font-medium text-bronze-strong  mb-3">
                  {isAI
                    ? S.moveConfirm(moveAgentCount, u.service_name, selectedTarget.name)
                    : S.moveSandboxConfirm(moveAgentCount, moveAppCount, moveInheritedCount, u.service_name, selectedTarget.name)}
                </p>
                <div className="flex gap-2">
                  <ButtonApp
                    label={S.moveCancel}
                    type="button"
                    ref={cancelBtnRef}
                    disabled={moving}
                    onClick={cancelConfirm}
                    variant="secondary"
                    size="medium"
                  />
                  <ButtonApp
                    label={moving ? S.moveConfirming : S.moveConfirmButton}
                    type="button"
                    disabled={moving}
                    onClick={() => void handleMove()}
                    variant="primary"
                    size="medium"
                  />
                  
                </div>
              </div>
            )}
          </div>
        )}
        <p className="mt-3 text-xs text-fg-secondary dark:text-fg-secondary-dark">
          {isAI ? S.moveNote : S.moveSandboxNote}
        </p>
      </section>
    );
  }

  function renderBody(u: ServiceUsage) {
    const isSandbox = kind === 'sandbox';
    const defaultApps = u.apps_using_as_default ?? [];
    const total =
      u.agents.length +
      u.silos.length +
      u.repositories.length +
      u.middlewares.length +
      u.scheduled_tasks.length +
      defaultApps.length;
    return (
      <>
        <div className="mb-4">
          {!isPanel && (
            <ServiceStatusBadge
              lifecycleStatus={u.lifecycle_status}
              endOfServiceAt={u.end_of_service_at}
              deprecationNotice={u.deprecation_notice}
            />
          )}
          {kind === 'embedding' && u.lifecycle_status !== 'active' && u.end_of_service_at && (
            <p className="mt-2 text-sm text-orange-800 dark:text-orange-200">
              {SERVICE_LIFECYCLE_STRINGS.embeddingWarning(formatEndOfServiceDate(u.end_of_service_at))}
            </p>
          )}
          {kind === 'embedding' && u.silos.length > 0 && (
            <p className="mt-2 text-sm text-fg-secondary dark:text-fg-secondary-dark">{S.reindexWarning}</p>
          )}
        </div>
        {total === 0 && (
          <p className="mb-4 text-sm text-fg-secondary dark:text-fg-secondary-dark">{S.nothing}</p>
        )}
        <Section title={S.sections.agents} count={u.agents.length}>
          {u.agents.map((a) => (
            <Entry
              key={a.agent_id}
              to={`${base(a.app_id)}/agents/${a.agent_id}`}
              name={a.name}
              detail={a.roles.map((r) => S.agentRoles[r] ?? r).join(', ')}
              canNavigate={canNavigate}
              appName={scopedApp(a.app_name)}
            />
          ))}
        </Section>
        {isSandbox && (
          <Section title={S.sections.appsDefault} count={defaultApps.length}>
            {defaultApps.map((a) => (
              <Entry
                key={a.app_id}
                to={`${base(a.app_id)}/settings`}
                name={a.app_name}
                canNavigate={canNavigate}
              />
            ))}
          </Section>
        )}
        {!isSandbox && (<>
        <Section title={S.sections.silos} count={u.silos.length}>
          {u.silos.map((s) => (
            <Entry
              key={s.silo_id}
              to={`${base(s.app_id)}/silos/${s.silo_id}`}
              name={s.name}
              detail={s.roles.map((r) => S.siloRoles[r] ?? r).join(', ')}
              canNavigate={canNavigate}
              appName={scopedApp(s.app_name)}
            />
          ))}
        </Section>
        <Section title={S.sections.repositories} count={u.repositories.length}>
          {u.repositories.map((r) => (
            <Entry
              key={r.repository_id}
              to={`${base(r.app_id)}/repositories/${r.repository_id}/detail`}
              name={r.name}
              canNavigate={canNavigate}
              appName={scopedApp(r.app_name)}
            />
          ))}
        </Section>
        <Section title={S.sections.middlewares} count={u.middlewares.length}>
          {u.middlewares.map((m) => (
            <Entry
              key={m.middleware_id}
              to={`${base(m.app_id)}/middlewares`}
              name={m.name}
              detail={m.middleware_type}
              canNavigate={canNavigate}
              appName={scopedApp(m.app_name)}
            />
          ))}
        </Section>
        </>)}
        <Section title={S.sections.scheduledTasks} count={u.scheduled_tasks.length}>
          {u.scheduled_tasks.map((t) => (
            <Entry
              key={t.task_id}
              to={`${base(t.app_id)}/scheduled-tasks/${t.task_id}`}
              name={t.name}
              canNavigate
              appName={scopedApp(t.app_name)}
            />
          ))}
        </Section>
        {renderMove(u)}
      </>
    );
  }

  const content = (
    <>
      {loading && !usage && (
        <p ref={loadStatusRef} tabIndex={-1} role="status" className="text-sm text-fg-secondary dark:text-fg-secondary-dark">
          {S.loading}
        </p>
      )}
      {error && (
        <div role="alert" className="rounded-lg border border-red-200 bg-red-50 dark:border-red-800 dark:bg-red-900/30 p-3 mb-4">
          <p className="text-sm text-red-800 dark:text-red-200">{error}</p>
          <button
            type="button"
            onClick={() => {
              setReloadKey((k) => k + 1);
              requestAnimationFrame(() => loadStatusRef.current?.focus());
            }}
            className="mt-2 text-sm font-medium text-red-800 dark:text-red-200 underline focus:outline-none focus:ring-2 focus:ring-red-500 rounded"
          >
            {S.retry}
          </button>
        </div>
      )}
      {moveMessage && (
          <div ref={messageRef} tabIndex={-1}>
            <Alert type={moveMessage.type} message={moveMessage.text} className="mb-4" />
          </div>
      )}
      {usage && !error && renderBody(usage)}
      {onDelete && usage && !error && (
        <p className="mt-4 text-sm text-fg dark:text-fg-dark">
          {S.deleteReview}
        </p>
      )}
      <div className="mt-4 flex justify-between">
        {onDelete && usage && !error ? (
          <ButtonApp
            label={deleting ? S.deleting : S.deleteButton}
            type="button"
            disabled={deleting || moving}
            onClick={() => void handleDelete()}
            variant="danger"
            size="medium"
          />
        ) : <span />}
        {!isPanel && (
          <ButtonApp
            label={S.close}
            type="button"
            disabled={deleting || moving}
            onClick={onClose}
            variant="secondary"
            size="medium"
          />
        )}
      </div>
    </>
  );

  if (isPanel) {
    return (
      <div className="px-1.5 pt-2">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <h3 className="text-base font-semibold text-fg dark:text-fg-dark">{S.title(serviceName)}</h3>
          {usage && !error && (
            <ServiceStatusBadge
              lifecycleStatus={usage.lifecycle_status}
              endOfServiceAt={usage.end_of_service_at}
              deprecationNotice={usage.deprecation_notice}
            />
          )}
        </div>
        {content}
      </div>
    );
  }

  return (
    <Modal isOpen onClose={onClose} title={S.title(serviceName)} size="large">
      {content}
    </Modal>
  );
}

export default ServiceUsageModal;
