import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { ThemeContext, type ColorMode } from './ThemeContext';
import type { ThemeConfig } from '../core/types';

const COLOR_MODE_STORAGE_KEY = 'mattin-color-mode';

// Storage can throw (private mode, blocked site data) — fall back to light.
function readStoredColorMode(): ColorMode {
  try {
    return localStorage.getItem(COLOR_MODE_STORAGE_KEY) === 'dark' ? 'dark' : 'light';
  } catch {
    return 'light';
  }
}

interface ThemeProviderProps {
  theme: ThemeConfig;
  children: React.ReactNode;
}

export const ThemeProvider: React.FC<ThemeProviderProps> = ({ theme, children }) => {
  const [currentTheme, setCurrentTheme] = useState<ThemeConfig>(theme);

  useEffect(() => {
    // Apply theme colors as CSS variables
    const root = document.documentElement;
    root.style.setProperty('--color-primary', currentTheme.colors.primary);
    root.style.setProperty('--color-secondary', currentTheme.colors.secondary);
    root.style.setProperty('--color-accent', currentTheme.colors.accent);
    root.style.setProperty('--color-background', currentTheme.colors.background);
    root.style.setProperty('--color-surface', currentTheme.colors.surface);
    root.style.setProperty('--color-text', currentTheme.colors.text);

    // Update favicon
    if (currentTheme.favicon) {
      const link = document.querySelector("link[rel*='icon']") as HTMLLinkElement;
      if (link) link.href = currentTheme.favicon;
    }

    // Update title
    document.title = currentTheme.name || 'Mattin AI';
  }, [currentTheme]);

  const [colorMode, setColorMode] = useState<ColorMode>(readStoredColorMode);

  useEffect(() => {
    document.documentElement.classList.toggle('dark', colorMode === 'dark');
    try {
      localStorage.setItem(COLOR_MODE_STORAGE_KEY, colorMode);
    } catch {
      // Persisting is best-effort only.
    }
  }, [colorMode]);

  const toggleColorMode = useCallback(() => {
    setColorMode((mode) => (mode === 'dark' ? 'light' : 'dark'));
  }, []);

  const contextValue = useMemo(() => ({
    theme: currentTheme,
    setTheme: setCurrentTheme,
    colorMode,
    toggleColorMode
  }), [currentTheme, colorMode, toggleColorMode]);

  return (
    <ThemeContext.Provider value={contextValue}>
      <div className={`theme-${currentTheme.name}`}>
        {children}
      </div>
    </ThemeContext.Provider>
  );
};
