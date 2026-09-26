import type { TimeseriesResponse } from '../../types/metrics';

const compact = new Intl.NumberFormat('en', { notation: 'compact', maximumFractionDigits: 1 });
const whole = new Intl.NumberFormat('en');

export const formatCount = (n: number): string => (Math.abs(n) >= 10_000 ? compact.format(n) : whole.format(n));

export const formatPercent = (ratio: number): string =>
  `${(ratio * 100).toFixed(ratio > 0 && ratio < 0.1 ? 1 : 0)}%`;

export function formatMs(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return '—';
  if (ms < 1000) return `${Math.round(ms)} ms`;
  return `${(ms / 1000).toFixed(ms < 10_000 ? 2 : 1)} s`;
}

/** Axis/tooltip label for a UTC bucket start, in the viewer's local time. */
export function formatBucket(ts: string, bucket: TimeseriesResponse['bucket'], withDate = false): string {
  const d = new Date(`${ts}Z`);
  if (bucket === '1d') return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
  const time = d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
  if (bucket === '1h' && !withDate) return time;
  return `${d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })} ${time}`;
}

export function formatDateTime(ts: string | null): string {
  if (!ts) return '—';
  return new Date(`${ts}Z`).toLocaleString(undefined, {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  });
}

/** Relative change vs the previous window; null when there is no baseline. */
export function relativeChange(current: number | null, previous: number | null): number | null {
  if (current === null || previous === null || previous === 0) return null;
  return (current - previous) / previous;
}
