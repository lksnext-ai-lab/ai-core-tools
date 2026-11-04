import { useEffect, useState } from 'react';

/** Milliseconds left until `deadline` (ISO timestamp), refreshed every second; 0 once it has passed. */
export function useCountdown(deadline: string | null): number {
  const target = deadline ? Date.parse(deadline) : Number.NaN;
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (Number.isNaN(target)) return undefined;
    setNow(Date.now());
    const id = window.setInterval(() => {
      const current = Date.now();
      setNow(current);
      if (current >= target) window.clearInterval(id);
    }, 1000);
    return () => window.clearInterval(id);
  }, [target]);

  return Number.isNaN(target) ? 0 : Math.max(0, target - now);
}
