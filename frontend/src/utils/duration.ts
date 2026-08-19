interface FormatDurationOptions {
  readonly showMillisecondsBelowSecond?: boolean;
}

export function formatDuration(
  milliseconds: number,
  { showMillisecondsBelowSecond = false }: FormatDurationOptions = {},
): string {
  const safeMilliseconds = Math.max(0, Math.round(milliseconds));

  if (showMillisecondsBelowSecond && safeMilliseconds < 1000) {
    return `${safeMilliseconds}ms`;
  }

  return `${(safeMilliseconds / 1000).toFixed(1)}s`;
}