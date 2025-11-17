import React from 'react';
import { useTheme } from '../../themes/ThemeContext';
import type { ThemeConfig } from '../../core/types';

interface ThemeSelectorProps {
  themes?: Record<string, ThemeConfig>;
  className?: string;
  showLabel?: boolean;
}

export const ThemeSelector: React.FC<ThemeSelectorProps> = ({
  themes = {},
  className = "",
  showLabel = true
}) => {
  const { theme, setTheme } = useTheme();

  const handleThemeChange = (themeName: string) => {
    const selectedTheme = themes[themeName];
    if (selectedTheme) {
      setTheme(selectedTheme);
    }
  };

  const availableThemes = Object.keys(themes);

  if (availableThemes.length <= 1) {
    return null;
  }

  return (
    <div className={`flex items-center space-x-2 ${className}`}>
      {showLabel && (
        <label htmlFor="theme-selector" className="text-sm font-medium text-gray-700">
          Theme:
        </label>
      )}
      <select
        id="theme-selector"
        value={theme.name}
        onChange={(e) => handleThemeChange(e.target.value)}
        className="px-3 py-1 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
      >
        {availableThemes.map((themeName) => (
          <option key={themeName} value={themeName}>
            {themes[themeName].name || themeName}
          </option>
        ))}
      </select>
    </div>
  );
};
