import { useEffect, useState } from 'react';

// Categorical slots 1-2 of the reference data-viz palette (validated light & dark:
// CVD ΔE 24.7, normal-vision ΔE 33.6, >= 3:1 contrast) plus the reserved status red.
const LIGHT = {
  primary: '#2a78d6',
  secondary: '#eb6834',
  critical: '#d03b3b',
  grid: '#e7e6e2',
  axis: '#52514e',
  surface: '#fcfcfb',
};
const DARK = {
  primary: '#3987e5',
  secondary: '#d95926',
  critical: '#d03b3b',
  grid: '#383835',
  axis: '#c3c2b7',
  surface: '#1a1a19',
};

export type ChartPalette = typeof LIGHT;

const isDark = () => typeof document !== 'undefined' && document.documentElement.classList.contains('dark');

/** Chart colors for the active theme; follows the `dark` class Tailwind uses. */
export function useChartPalette(): ChartPalette {
  const [dark, setDark] = useState(isDark);
  useEffect(() => {
    const observer = new MutationObserver(() => setDark(isDark()));
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] });
    return () => observer.disconnect();
  }, []);
  return dark ? DARK : LIGHT;
}
