import i18n from '../../i18n';
import type { TimeseriesResponse } from '../../types/metrics';

const locale = () => i18n.resolvedLanguage ?? i18n.language;

export const formatCount = (n: number): string => new Intl.NumberFormat(locale(), {
  notation: Math.abs(n) >= 10_000 ? 'compact' : 'standard',
  maximumFractionDigits: Math.abs(n) >= 10_000 ? 1 : 0,
}).format(n);

export const formatPercent = (ratio: number): string => {
  const fractionDigits = ratio > 0 && ratio < 0.1 ? 1 : 0;
  return new Intl.NumberFormat(locale(), {
    style: 'percent',
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  }).format(ratio);
};

export function formatMs(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return '—';
  if (ms < 1000) return `${new Intl.NumberFormat(locale(), { maximumFractionDigits: 0 }).format(Math.round(ms))} ms`;
  return `${new Intl.NumberFormat(locale(), { maximumFractionDigits: ms < 10_000 ? 2 : 1 }).format(ms / 1000)} s`;
}

/** Axis/tooltip label for a UTC bucket start, in the viewer's local time. */
export function formatBucket(ts: string, bucket: TimeseriesResponse['bucket'], withDate = false): string {
  const d = new Date(`${ts}Z`);
  if (bucket === '1d') return d.toLocaleDateString(locale(), { month: 'short', day: 'numeric' });
  const time = d.toLocaleTimeString(locale(), { hour: '2-digit', minute: '2-digit' });
  if (bucket === '1h' && !withDate) return time;
  return `${d.toLocaleDateString(locale(), { month: 'short', day: 'numeric' })} ${time}`;
}

export function formatDateTime(ts: string | null): string {
  if (!ts) return '—';
  return new Date(`${ts}Z`).toLocaleString(locale(), {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  });
}

/** Relative change vs the previous window; null when there is no baseline. */
export function relativeChange(current: number | null, previous: number | null): number | null {
  if (current === null || previous === null || previous === 0) return null;
  return (current - previous) / previous;
}
