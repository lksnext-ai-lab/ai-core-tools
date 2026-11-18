import { useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { AlertCircle, Users } from 'lucide-react';
import { apiService, type MyGroup, type MyGroupApp } from '../services/api';
import Alert from '../components/ui/Alert';

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
    <div className="mx-auto max-w-6xl space-y-6 p-4 sm:p-6">
      <header>
        <h1 className="flex items-center gap-2 text-2xl font-semibold text-gray-900 dark:text-white">
          <Users aria-hidden="true" className="h-6 w-6 text-indigo-600 dark:text-indigo-400" />
          My Groups
        </h1>
        <p className="mt-2 text-sm text-gray-600 dark:text-gray-300">
          View groups provisioned to your account and the app access each group contributes. This page is read-only.
        </p>
      </header>

      {groupError && (
        <Alert type="error" title="Groups could not be loaded" message={(
          <div>
            <p>{groupError}</p>
            <button type="button" onClick={() => void loadGroups(0, false)}
              className="mt-2 rounded underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2">
              Retry loading groups
            </button>
          </div>
        )} />
      )}

      <div className="grid gap-6 lg:grid-cols-[minmax(16rem,1fr)_2fr]">
        <section aria-labelledby="my-groups-heading" className="rounded-lg border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800">
          <h2 id="my-groups-heading" className="text-lg font-semibold text-gray-900 dark:text-white">Your groups</h2>
          {groupLoading ? (
            <p className="mt-4" role="status" aria-live="polite">Loading your groups…</p>
          ) : groups.length === 0 && !groupError ? (
            <p className="mt-4 text-sm text-gray-600 dark:text-gray-300">You do not currently have any eligible groups.</p>
          ) : (
            <ul className="mt-3 divide-y divide-gray-200 dark:divide-gray-700">
              {groups.map((group) => (
                <li key={group.group_id} className="py-2">
                  <button type="button" onClick={() => void loadGroupApps(group, 0, false)}
                    aria-current={selectedGroup?.group_id === group.group_id ? 'true' : undefined}
                    className={`w-full rounded-md p-3 text-left hover:bg-gray-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-600 dark:hover:bg-gray-700 ${
                      selectedGroup?.group_id === group.group_id ? 'bg-indigo-50 dark:bg-indigo-950' : ''
                    }`}>
                    <span className="block font-medium text-gray-900 dark:text-white">{group.display_name}</span>
                    <span className="mt-1 block break-all text-xs text-gray-600 dark:text-gray-300">
                      Group ID: {group.group_id}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
          {groupHasMore && (
            <button type="button" disabled={groupLoading || groupsLoadingMore} onClick={() => void loadGroups(groupOffset, true)}
              className="mt-3 rounded px-3 py-2 text-sm font-medium text-indigo-700 hover:bg-indigo-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-600 disabled:opacity-60 dark:text-indigo-300 dark:hover:bg-gray-700">
              {groupsLoadingMore ? 'Loading…' : 'Load more groups'}
            </button>
          )}
          {groupsLoadingMore && <span className="sr-only" role="status">Loading more groups</span>}
        </section>

        <section aria-labelledby="group-apps-heading" className="min-w-0 rounded-lg border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800">
          <h2 id="group-apps-heading" className="text-lg font-semibold text-gray-900 dark:text-white">
            {selectedGroup ? `Apps for ${selectedGroup.display_name}` : 'Group app access'}
          </h2>
          {appsError && (
            <div className="mt-4">
              <Alert type="error" title="Group apps could not be loaded" message={appsError} />
              {selectedGroup && (
                <button type="button" onClick={() => void loadGroupApps(selectedGroup, 0, false)}
                  className="mt-2 rounded px-3 py-2 text-sm underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-600">
                  Retry loading apps
                </button>
              )}
            </div>
          )}
          {!selectedGroup ? (
            <p className="mt-4 text-sm text-gray-600 dark:text-gray-300">Select a group to view its app access.</p>
          ) : appsLoading ? (
            <p className="mt-4" role="status" aria-live="polite">Loading apps for this group…</p>
          ) : groupApps.length === 0 && !appsError ? (
            <p className="mt-4 text-sm text-gray-600 dark:text-gray-300">This group has no active app access policies.</p>
          ) : (
            <div className="mt-4 space-y-3">
              {groupApps.map((item) => {
                const differs = contributionDiffers(item.contribution, item.effective_role);
                return (
                  <Link
                    key={item.app_id}
                    to={`/apps/${item.app_id}`}
                    className="block rounded-md border border-gray-200 p-4 hover:bg-gray-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-600 dark:border-gray-700 dark:hover:bg-gray-700"
                  >
                    <h3 className="font-medium text-gray-900 dark:text-white">
                      {item.app_name || `App ${item.app_id}`}
                    </h3>
                    <p className="mt-1 break-all text-sm text-gray-600 dark:text-gray-300">App ID: {item.app_id}</p>
                    <p className="mt-2 text-sm text-gray-700 dark:text-gray-200">
                      This group contributes: <span className="font-semibold">{item.contribution}</span>
                    </p>
                    {differs && item.effective_role && (
                      <p className="mt-1 text-sm text-gray-700 dark:text-gray-200">
                        Your effective app role: <span className="font-semibold">{item.effective_role.toUpperCase()}</span>
                      </p>
                    )}
                  </Link>
                );
              })}
            </div>
          )}
          {appsHaveMore && (
            <button type="button" disabled={appsLoading || appsLoadingMore} onClick={() => selectedGroup && void loadGroupApps(selectedGroup, appsOffset, true)}
              className="mt-4 rounded px-3 py-2 text-sm font-medium text-indigo-700 hover:bg-indigo-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-600 disabled:opacity-60 dark:text-indigo-300 dark:hover:bg-gray-700">
              {appsLoadingMore ? 'Loading…' : 'Load more apps'}
            </button>
          )}
          {appsLoadingMore && <span className="sr-only" role="status">Loading more apps</span>}
        </section>
      </div>
      <div className="sr-only" role="status" aria-live="polite">
        {groupLoading ? 'Loading groups' : `${groups.length} of ${groupTotal} groups loaded`}
      </div>
      <div className="sr-only" role="status" aria-live="polite">
        {appsLiveMessage}
      </div>
      <AlertIconHint />
    </div>
  );
}

function AlertIconHint() {
  return (
    <p className="flex items-start gap-2 text-xs text-gray-500 dark:text-gray-400">
      <AlertCircle aria-hidden="true" className="h-4 w-4 shrink-0" />
      Group access shown here is informational and does not change your app role or account permissions.
    </p>
  );
}

export default MyGroupsPage;
