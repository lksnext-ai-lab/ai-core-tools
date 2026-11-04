import { useEffect, useRef } from 'react';

const POLL_INTERVAL_MS = 10_000;
const MAX_POLLS = 12;

/**
 * After an approval expires the server rejects it and the agent writes its answer (within
 * about a minute). Poll until the conversation no longer reports that approval, then call
 * `onResolved` so the page can reload the conversation.
 */
export function useApprovalExpiryWatch(
  expiredApprovalId: string | null,
  fetchPendingApprovalId: () => Promise<string | null>,
  onResolved: () => void,
): void {
  const fetchRef = useRef(fetchPendingApprovalId);
  const resolvedRef = useRef(onResolved);
  useEffect(() => {
    fetchRef.current = fetchPendingApprovalId;
    resolvedRef.current = onResolved;
  }, [fetchPendingApprovalId, onResolved]);

  useEffect(() => {
    if (!expiredApprovalId) return undefined;
    let polls = 0;
    const id = window.setInterval(() => {
      polls += 1;
      fetchRef.current()
        .then((pendingId) => {
          if (pendingId !== expiredApprovalId || polls >= MAX_POLLS) {
            window.clearInterval(id);
            resolvedRef.current();
          }
        })
        .catch(() => {
          if (polls >= MAX_POLLS) window.clearInterval(id);
        });
    }, POLL_INTERVAL_MS);
    return () => window.clearInterval(id);
  }, [expiredApprovalId]);
}
