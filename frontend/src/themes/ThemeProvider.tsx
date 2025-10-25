import React, { useState, useEffect, useMemo } from 'react';
import { ThemeContext } from './ThemeContext';
import type { ThemeConfig } from '../core/types';

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

  const contextValue = useMemo(() => ({
    theme: currentTheme,
    setTheme: setCurrentTheme
  }), [currentTheme]);

  return (
    <ThemeContext.Provider value={contextValue}>
      <div className={`theme-${currentTheme.name}`}>
        {children}
      </div>
    </ThemeContext.Provider>
  );
};
