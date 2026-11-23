import { createContext, useContext } from 'react';
import type { ThemeConfig } from '../core/types';

export type ColorMode = 'light' | 'dark';

interface ThemeContextType {
  theme: ThemeConfig;
  setTheme: (theme: ThemeConfig) => void;
  /** Design v3 light/dark mode — toggles the `dark` class on <html>. */
  colorMode: ColorMode;
  toggleColorMode: () => void;
}

export const ThemeContext = createContext<ThemeContextType | undefined>(undefined);

export const useTheme = () => {
  const context = useContext(ThemeContext);
  if (context === undefined) {
    throw new Error('useTheme must be used within a ThemeProvider');
  }
  return context;
};
