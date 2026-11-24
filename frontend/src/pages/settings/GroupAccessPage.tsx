import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react';
import { useParams } from 'react-router-dom';
import { ShieldCheck, Users } from 'lucide-react';
import Alert from '../../components/ui/Alert';
import { CardApp } from '../../components/ui/CardApp';
import { StatusBadge } from '../../components/ui/Badge';
import ButtonApp from '../../components/ui/ButtonApp';
import { LoadingState } from '../../components/ui/LoadingState';
import Title from '../../components/ui/Title';
import { useConfirm } from '../../contexts/ConfirmContext';
import { useAppRole } from '../../hooks/useAppRole';
import { apiService, type EligibleGroup, type GroupAppRole, type GroupAppRule } from '../../services/api';
import { AppRole } from '../../types/roles';

const GROUP_PAGE_SIZE = 50;
const RULE_PAGE_SIZE = 100;

function GroupAccessPage() {
  const { appId: appIdParam } = useParams();
  const appId = Number(appIdParam);
  const { userRole, loading: roleLoading } = useAppRole(appIdParam);
  const canManage = userRole === AppRole.OWNER || userRole === AppRole.ADMINISTRATOR;
  const confirm = useConfirm();

  const [groups, setGroups] = useState<EligibleGroup[]>([]);
  const [groupsTotal, setGroupsTotal] = useState(0);
  const [groupsOffset, setGroupsOffset] = useState(0);
  const [rules, setRules] = useState<GroupAppRule[]>([]);
  const [rulesOffset, setRulesOffset] = useState(0);
  const [hasMoreRules, setHasMoreRules] = useState(false);
  const [selectedGroupId, setSelectedGroupId] = useState('');
  const [newRole, setNewRole] = useState<GroupAppRole>('viewer');
  const [loading, setLoading] = useState(true);
  const [loadingMoreGroups, setLoadingMoreGroups] = useState(false);
  const [loadingMoreRules, setLoadingMoreRules] = useState(false);
  const [pendingAction, setPendingAction] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState('');
  const appGeneration = useRef(0);

  const loadManagementData = useCallback(async (generation: number) => {
    if (!Number.isSafeInteger(appId) || appId <= 0) {
      if (appGeneration.current === generation) {
        setError('Invalid app identifier.');
        setLoading(false);
      }
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const [groupPage, rulePage] = await Promise.all([
        apiService.getEligibleGroups(appId, 0, GROUP_PAGE_SIZE),
        apiService.getGroupAppRules(appId, 0, RULE_PAGE_SIZE),
      ]);
      if (appGeneration.current !== generation) return;
      setGroups(groupPage.items);
      setGroupsTotal(groupPage.total);
      setGroupsOffset(groupPage.items.length);
      setRules(rulePage);
      setRulesOffset(rulePage.length);
      setHasMoreRules(rulePage.length === RULE_PAGE_SIZE);
    } catch (loadError) {
      if (appGeneration.current === generation) {
        setError(loadError instanceof Error ? loadError.message : 'Unable to load group access settings.');
      }
    } finally {
      if (appGeneration.current === generation) setLoading(false);
    }
  }, [appId]);

  useEffect(() => {
    const generation = ++appGeneration.current;
    setGroups([]);
    setGroupsTotal(0);
    setGroupsOffset(0);
    setRules([]);
    setRulesOffset(0);
    setHasMoreRules(false);
    setSelectedGroupId('');
    setPendingAction(null);
    setError(null);
    setStatus('');
    setLoading(canManage);
    setLoadingMoreGroups(false);
    setLoadingMoreRules(false);
    if (canManage) void loadManagementData(generation);
    return () => {
      if (appGeneration.current === generation) appGeneration.current += 1;
    };
  }, [canManage, loadManagementData]);

  async function loadMoreGroups() {
    const generation = appGeneration.current;
    setLoadingMoreGroups(true);
    setError(null);
    try {
      const page = await apiService.getEligibleGroups(appId, groupsOffset, GROUP_PAGE_SIZE);
      if (appGeneration.current !== generation) return;
      setGroups((current) => [...current, ...page.items]);
      setGroupsOffset(groupsOffset + page.items.length);
      setGroupsTotal(page.total);
    } catch (loadError) {
      if (appGeneration.current === generation) {
        setError(loadError instanceof Error ? loadError.message : 'Unable to load more eligible groups.');
      }
    } finally {
      if (appGeneration.current === generation) setLoadingMoreGroups(false);
    }
  }

  async function loadMoreRules() {
    const generation = appGeneration.current;
    setLoadingMoreRules(true);
    setError(null);
    try {
      const page = await apiService.getGroupAppRules(appId, rulesOffset, RULE_PAGE_SIZE);
      if (appGeneration.current !== generation) return;
      setRules((current) => [...current, ...page]);
      setRulesOffset(rulesOffset + page.length);
      setHasMoreRules(page.length === RULE_PAGE_SIZE);
    } catch (loadError) {
      if (appGeneration.current === generation) {
        setError(loadError instanceof Error ? loadError.message : 'Unable to load more policies.');
      }
    } finally {
      if (appGeneration.current === generation) setLoadingMoreRules(false);
    }
  }

  async function refreshAfterMutation(message: string, generation: number) {
    if (appGeneration.current !== generation) return;
    setStatus(message);
    setSelectedGroupId('');
    await loadManagementData(generation);
  }

  async function createRule(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const groupId = Number(selectedGroupId);
    if (!Number.isSafeInteger(groupId) || groupId <= 0) return;
    const generation = appGeneration.current;
    setPendingAction('create');
    setError(null);
    setStatus('');
    try {
      await apiService.createGroupAppRule(appId, groupId, newRole);
      await refreshAfterMutation('Group access policy created.', generation);
    } catch (actionError) {
      if (appGeneration.current === generation) {
        setError(actionError instanceof Error ? actionError.message : 'Unable to create the group access policy.');
      }
    } finally {
      if (appGeneration.current === generation) setPendingAction(null);
    }
  }

  async function changeRuleRole(rule: GroupAppRule, role: GroupAppRole) {
    const generation = appGeneration.current;
    setPendingAction(`role-${rule.id}`);
    setError(null);
    setStatus('');
    try {
      await apiService.updateGroupAppRule(appId, rule.id, role);
      await refreshAfterMutation('Group access role updated.', generation);
    } catch (actionError) {
      if (appGeneration.current === generation) {
        setError(actionError instanceof Error ? actionError.message : 'Unable to update the group access role.');
      }
    } finally {
      if (appGeneration.current === generation) setPendingAction(null);
    }
  }

  async function revokeRule(rule: GroupAppRule) {
    const generation = appGeneration.current;
    const accepted = await confirm({
      title: 'Revoke group app access?',
      message: `Revoke this group's ${rule.role.toUpperCase()} access to the app? The change takes effect immediately.`,
      confirmLabel: 'Revoke access',
      variant: 'danger',
    });
    if (!accepted || appGeneration.current !== generation) return;

    setPendingAction(`revoke-${rule.id}`);
    setError(null);
    setStatus('');
    try {
      await apiService.revokeGroupAppRule(appId, rule.id);
      await refreshAfterMutation('Group app access revoked.', generation);
    } catch (actionError) {
      if (appGeneration.current === generation) {
        setError(actionError instanceof Error ? actionError.message : 'Unable to revoke group app access.');
      }
    } finally {
      if (appGeneration.current === generation) setPendingAction(null);
    }
  }

  if (roleLoading) {
    return <LoadingState variant="page" message="Checking app permissions…" />;
  }

  if (!canManage) {
    return (
      <div className="space-y-6 p-6">
        <Title variant="titSecundario" titulo="Group access policies" />
        <Alert
          type="warning"
          title="Access restricted"
          message="Only this app's owner or an accepted app administrator can manage group access policies."
        />
      </div>
    );
  }

  const activeRuleGroupIds = new Set(rules.filter((rule) => rule.is_active).map((rule) => rule.group_id));

  return (
    <div className="space-y-8 p-6">
      <header>
        <Title
          variant="titSecundario"
          titulo="Group access policies"
          subtitulo="Grant eligible groups app-scoped VIEWER or EDITOR access. These policies are separate from individual app collaborations."
        />
      </header>

      {error && (
        <Alert type="error" title="Group access action failed" message={(
          <div>
            <p>{error}</p>
            <button type="button" onClick={() => void loadManagementData(appGeneration.current)}
              className="mt-2 rounded font-medium text-ink underline hover:decoration-2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent dark:text-ink-dark dark:focus-visible:outline-accent-dark">
              Retry loading policies
            </button>
          </div>
        )} />
      )}
      {status && <Alert type="success" message={status} polite />}

      {loading ? (
        <LoadingState variant="section" message="Loading eligible groups and policies…" />
      ) : (
        <>
          <CardApp
            icon={Users}
            titulo="Grant group access"
            subtitulo="Only groups from your active linked provisioning connection are listed."
            className="px-6 py-5"
          >
            {groups.length === 0 ? (
              <p className="mt-4 text-sm text-fg-secondary dark:text-fg-secondary-dark">
                No eligible groups are available. An active linked provisioning connection is required.
              </p>
            ) : (
              <form onSubmit={(event) => void createRule(event)} className="mt-4 grid gap-4 sm:grid-cols-[minmax(12rem,1fr)_10rem_auto] sm:items-end">
                <div>
                  <label htmlFor="eligible-group" className="mb-1 block text-sm font-medium text-fg dark:text-fg-dark">Group</label>
                  <select id="eligible-group" value={selectedGroupId} onChange={(event) => setSelectedGroupId(event.target.value)}
                    required disabled={pendingAction !== null}
                    className="w-full rounded-lg border border-line-strong bg-surface px-3 py-2 text-sm text-fg focus:border-accent focus:outline-none dark:border-line-strong-dark dark:bg-surface-dark dark:text-fg-dark dark:focus:border-accent-dark">
                    <option value="">Select a group</option>
                    {groups.map((group) => (
                      <option key={group.group_id} value={group.group_id} disabled={activeRuleGroupIds.has(group.group_id)}>
                        {group.display_name} (ID: {group.group_id}){activeRuleGroupIds.has(group.group_id) ? ' — already active' : ''}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label htmlFor="group-role" className="mb-1 block text-sm font-medium text-fg dark:text-fg-dark">App role</label>
                  <select id="group-role" value={newRole} onChange={(event) => setNewRole(event.target.value as GroupAppRole)}
                    disabled={pendingAction !== null}
                    className="w-full rounded-lg border border-line-strong bg-surface px-3 py-2 text-sm text-fg focus:border-accent focus:outline-none dark:border-line-strong-dark dark:bg-surface-dark dark:text-fg-dark dark:focus:border-accent-dark">
                    <option value="viewer">VIEWER</option>
                    <option value="editor">EDITOR</option>
                  </select>
                </div>
                <ButtonApp
                  type="submit"
                  disabled={!selectedGroupId || pendingAction !== null}
                  loading={pendingAction === 'create'}
                  label={pendingAction === 'create' ? 'Saving…' : 'Grant access'}
                />
                {pendingAction === 'create' && <span className="sr-only" role="status">Saving group access policy</span>}
              </form>
            )}
            {groups.length < groupsTotal && (
              <button type="button" disabled={loadingMoreGroups || pendingAction !== null} onClick={() => void loadMoreGroups()}
                className="mt-3 rounded-md px-3 py-2 text-sm font-medium text-ink hover:bg-surface-hover focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent disabled:opacity-60 dark:text-ink-dark dark:hover:bg-surface-hover-dark dark:focus-visible:outline-accent-dark">
                {loadingMoreGroups ? 'Loading groups…' : 'Load more eligible groups'}
              </button>
            )}
          </CardApp>

          <CardApp
            icon={ShieldCheck}
            titulo="Current group policies"
            className="px-6 py-5"
          >
            {rules.length === 0 ? (
              <p className="mt-3 text-sm text-fg-secondary dark:text-fg-secondary-dark">No group policies are recorded for this connection.</p>
            ) : (
              <ul className="mt-3 divide-y divide-line dark:divide-line-dark">
                {rules.map((rule) => {
                  const pending = pendingAction === `role-${rule.id}` || pendingAction === `revoke-${rule.id}`;
                  return (
                    <li key={rule.id} className="flex flex-col gap-3 py-4 sm:flex-row sm:items-center sm:justify-between">
                      <div>
                        <p className="font-medium text-fg dark:text-fg-dark">{rule.group_display_name}</p>
                        <p className="mt-1 break-all text-xs text-fg-tertiary dark:text-fg-tertiary-dark">Group ID: {rule.group_id}</p>
                        <StatusBadge
                          status={rule.is_active ? 'active' : 'inactive'}
                          customLabel={rule.is_active ? 'Active' : 'Revoked'}
                          className="mt-2"
                        />
                      </div>
                      <div className="flex flex-wrap items-center gap-3">
                        {rule.is_active ? (
                          <>
                            <label htmlFor={`policy-role-${rule.id}`} className="sr-only">App role for {rule.group_display_name}</label>
                            <select id={`policy-role-${rule.id}`} value={rule.role}
                              onChange={(event) => void changeRuleRole(rule, event.target.value as GroupAppRole)}
                              disabled={pendingAction !== null}
                              className="rounded-lg border border-line-strong bg-surface px-3 py-2 text-sm text-fg focus:border-accent focus:outline-none dark:border-line-strong-dark dark:bg-surface-dark dark:text-fg-dark dark:focus:border-accent-dark">
                              <option value="viewer">VIEWER</option>
                              <option value="editor">EDITOR</option>
                            </select>
                            <ButtonApp
                              label={pendingAction === `revoke-${rule.id}` ? 'Revoking…' : 'Revoke'}
                              variant="danger"
                              size="control"
                              disabled={pendingAction !== null}
                              loading={pendingAction === `revoke-${rule.id}`}
                              onClick={() => void revokeRule(rule)}
                            />
                          </>
                        ) : (
                          <span className="text-sm text-fg-tertiary dark:text-fg-tertiary-dark">Inactive policy</span>
                        )}
                        {pending && <span role="status" aria-live="polite" className="text-sm text-fg-secondary dark:text-fg-secondary-dark">Saving…</span>}
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
            {hasMoreRules && (
              <button type="button" disabled={loadingMoreRules || pendingAction !== null} onClick={() => void loadMoreRules()}
                className="mt-3 rounded-md px-3 py-2 text-sm font-medium text-ink hover:bg-surface-hover focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent disabled:opacity-60 dark:text-ink-dark dark:hover:bg-surface-hover-dark dark:focus-visible:outline-accent-dark">
                {loadingMoreRules ? 'Loading policies…' : 'Load more policies'}
              </button>
            )}
          </CardApp>
        </>
      )}
    </div>
  );
}

export default GroupAccessPage;
