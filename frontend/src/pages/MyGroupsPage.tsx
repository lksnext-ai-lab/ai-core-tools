import { useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { AlertCircle } from 'lucide-react';
import { apiService, type MyGroup, type MyGroupApp } from '../services/api';
import Alert from '../components/ui/Alert';
import ButtonApp from '../components/ui/ButtonApp';
import CardApp from '../components/ui/CardApp';
import LoadingState from '../components/ui/LoadingState';
import Title from '../components/ui/Title';

const PAGE_SIZE = 50;

function MyGroupsPage() {
  const [groups, setGroups] = useState<MyGroup[]>([]);
  const [groupTotal, setGroupTotal] = useState(0);
  const [groupOffset, setGroupOffset] = useState(0);
  const [selectedGroup, setSelectedGroup] = useState<MyGroup | null>(null);
  const [groupLoading, setGroupLoading] = useState(true);
  const [groupsLoadingMore, setGroupsLoadingMore] = useState(false);
  const [groupError, setGroupError] = useState<string | null>(null);
  const [groupApps, setGroupApps] = useState<MyGroupApp[]>([]);
  const [appsTotal, setAppsTotal] = useState(0);
  const [appsOffset, setAppsOffset] = useState(0);
  const [appsLoading, setAppsLoading] = useState(false);
  const [appsLoadingMore, setAppsLoadingMore] = useState(false);
  const [appsError, setAppsError] = useState<string | null>(null);
  const groupRequest = useRef(0);
  const appRequest = useRef(0);

  const loadGroups = useCallback(async (offset: number, append: boolean) => {
    const requestId = ++groupRequest.current;
    if (append) setGroupsLoadingMore(true);
    else {
      setGroupLoading(true);
      setGroupsLoadingMore(false);
      setGroupError(null);
    }
    try {
      const page = await apiService.getMyGroups(offset, PAGE_SIZE);
      if (requestId !== groupRequest.current) return;
      setGroups((current) => append ? [...current, ...page.items] : page.items);
      setGroupTotal(page.total);
      setGroupOffset(offset + page.items.length);
    } catch (error) {
      if (requestId === groupRequest.current) {
        setGroupError(error instanceof Error ? error.message : 'Unable to load your groups.');
      }
    } finally {
      if (requestId === groupRequest.current) {
        setGroupLoading(false);
        setGroupsLoadingMore(false);
      }
    }
  }, []);

  const loadGroupApps = useCallback(async (group: MyGroup, offset: number, append: boolean) => {
    const requestId = ++appRequest.current;
    setSelectedGroup(group);
    setAppsError(null);
    if (append) setAppsLoadingMore(true);
    else {
      setAppsLoading(true);
      setAppsLoadingMore(false);
      setGroupApps([]);
      setAppsTotal(0);
      setAppsOffset(0);
    }
    try {
      const page = await apiService.getMyGroupApps(group.group_id, offset, PAGE_SIZE);
      if (requestId !== appRequest.current) return;
      setGroupApps((current) => append ? [...current, ...page.items] : page.items);
      setAppsTotal(page.total);
      setAppsOffset(offset + page.items.length);
    } catch (error) {
      if (requestId === appRequest.current) {
        setAppsError(error instanceof Error ? error.message : 'Unable to load apps for this group.');
      }
    } finally {
      if (requestId === appRequest.current) {
        setAppsLoading(false);
        setAppsLoadingMore(false);
      }
    }
  }, []);

  useEffect(() => {
    void loadGroups(0, false);
  }, [loadGroups]);

  function contributionDiffers(contribution: string, effectiveRole: string | null) {
    if (!effectiveRole) return false;
    return effectiveRole.toLowerCase() !== contribution.toLowerCase();
  }

  const groupHasMore = groups.length < groupTotal;
  const appsHaveMore = groupApps.length < appsTotal;
  let appsLiveMessage = '';
  if (appsLoading) {
    appsLiveMessage = 'Loading selected group apps';
  } else if (selectedGroup) {
    appsLiveMessage = `${groupApps.length} of ${appsTotal} apps loaded for ${selectedGroup.display_name}`;
  }

  return (
    <div className="space-y-6">
      <Title
        variant="titSecundario"
        titulo="My Groups"
        subtitulo="View groups provisioned to your account and the app access each group contributes. This page is read-only."
      />

      {groupError && (
        <Alert type="error" title="Groups could not be loaded" message={(
          <div className="space-y-2">
            <p>{groupError}</p>
            <ButtonApp
              label="Retry loading groups"
              variant="muted"
              size="small"
              onClick={() => void loadGroups(0, false)}
            />
          </div>
        )} />
      )}

      <div className="grid gap-5 lg:grid-cols-[minmax(16rem,1fr)_2fr]">
        <CardApp className="min-w-0">
          <div className="mb-4">
            <h2 className="font-display text-[17px] font-medium leading-8 text-fg dark:text-fg-dark">Your groups</h2>
            <p className="text-sm text-fg-secondary dark:text-fg-secondary-dark">
              Select a group to review the app access it contributes.
            </p>
          </div>
          {groupLoading ? (
            <LoadingState message="Loading your groups…" variant="section" />
          ) : groups.length === 0 && !groupError ? (
            <p className="text-sm text-fg-secondary dark:text-fg-secondary-dark">You do not currently have any eligible groups.</p>
          ) : (
            <ul className="divide-y divide-line dark:divide-line-dark">
              {groups.map((group) => (
                <li key={group.group_id} className="py-2 first:pt-0 last:pb-0">
                  <button type="button" onClick={() => void loadGroupApps(group, 0, false)}
                    aria-pressed={selectedGroup?.group_id === group.group_id}
                    className={`w-full rounded-md border px-3 py-3 text-left transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink dark:focus-visible:outline-ink-dark ${
                      selectedGroup?.group_id === group.group_id
                        ? 'border-bg-soft bg-surface-hover dark:border-bronze-border-dark dark:bg-surface-hover-dark'
                        : 'border-transparent hover:bg-surface-hover dark:hover:bg-surface-hover-dark'
                    }`}>
                    <span className="block font-display font-medium text-fg dark:text-fg-dark">{group.display_name}</span>
                    <span className="mt-1 block break-all text-xs text-fg-tertiary dark:text-fg-tertiary-dark">
                      Group ID: {group.group_id}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
          {groupHasMore && (
            <ButtonApp
              label="Load more groups"
              variant="muted"
              size="small"
              className="mt-3"
              disabled={groupLoading}
              loading={groupsLoadingMore}
              onClick={() => void loadGroups(groupOffset, true)}
            />
          )}
          {groupsLoadingMore && <output className="sr-only" aria-live="polite">Loading more groups</output>}
        </CardApp>

        <CardApp className="min-w-0">
          <div className="mb-4">
            <h2 className="font-display text-[17px] font-medium leading-8 text-fg dark:text-fg-dark">
              {selectedGroup ? `Apps for ${selectedGroup.display_name}` : 'Group app access'}
            </h2>
            <p className="text-sm text-fg-secondary dark:text-fg-secondary-dark">
              Review each group's contribution and your effective app role.
            </p>
          </div>
          {appsError && (
            <div className="mb-4 space-y-2">
              <Alert type="error" title="Group apps could not be loaded" message={appsError} />
              {selectedGroup && (
                <ButtonApp
                  label="Retry loading apps"
                  variant="muted"
                  size="small"
                  onClick={() => void loadGroupApps(selectedGroup, 0, false)}
                />
              )}
            </div>
          )}
          {!selectedGroup ? (
            <p className="text-sm text-fg-secondary dark:text-fg-secondary-dark">Select a group to view its app access.</p>
          ) : appsLoading ? (
            <LoadingState message="Loading apps for this group…" variant="section" />
          ) : groupApps.length === 0 && !appsError ? (
            <p className="text-sm text-fg-secondary dark:text-fg-secondary-dark">This group has no active app access policies.</p>
          ) : (
            <div className="space-y-3">
              {groupApps.map((item) => {
                const differs = contributionDiffers(item.contribution, item.effective_role);
                return (
                  <Link
                    key={item.app_id}
                    to={`/apps/${item.app_id}`}
                    className="block rounded-md focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink dark:focus-visible:outline-ink-dark"
                  >
                    <CardApp variant="canvas" className="gap-1 transition-colors hover:bg-surface-hover dark:hover:bg-surface-hover-dark">
                      <h3 className="font-display text-base font-medium text-fg dark:text-fg-dark">
                        {item.app_name || `App ${item.app_id}`}
                      </h3>
                      <p className="break-all text-xs text-fg-tertiary dark:text-fg-tertiary-dark">App ID: {item.app_id}</p>
                      <p className="mt-2 text-sm text-fg-secondary dark:text-fg-secondary-dark">
                        This group contributes: <span className="font-semibold text-fg dark:text-fg-dark">{item.contribution}</span>
                      </p>
                      {differs && item.effective_role && (
                        <p className="text-sm text-fg-secondary dark:text-fg-secondary-dark">
                          Your effective app role: <span className="font-semibold text-fg dark:text-fg-dark">{item.effective_role.toUpperCase()}</span>
                        </p>
                      )}
                    </CardApp>
                  </Link>
                );
              })}
            </div>
          )}
          {appsHaveMore && (
            <ButtonApp
              label="Load more apps"
              variant="muted"
              size="small"
              className="mt-4"
              disabled={appsLoading}
              loading={appsLoadingMore}
              onClick={() => selectedGroup && void loadGroupApps(selectedGroup, appsOffset, true)}
            />
          )}
          {appsLoadingMore && <output className="sr-only" aria-live="polite">Loading more apps</output>}
        </CardApp>
      </div>
      <output className="sr-only" aria-live="polite">
        {groupLoading ? 'Loading groups' : `${groups.length} of ${groupTotal} groups loaded`}
      </output>
      <output className="sr-only" aria-live="polite">
        {appsLiveMessage}
      </output>
      <AlertIconHint />
    </div>
  );
}

function AlertIconHint() {
  return (
    <p className="flex items-start gap-2 rounded-md bg-canvas-alt px-4 py-3 text-xs text-fg-secondary dark:bg-canvas-alt-dark dark:text-fg-secondary-dark">
      <AlertCircle aria-hidden="true" className="h-4 w-4 shrink-0 text-fg-tertiary dark:text-fg-tertiary-dark" />
      Group access shown here is informational and does not change your app role or account permissions.
    </p>
  );
}

export default MyGroupsPage;
