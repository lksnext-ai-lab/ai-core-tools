import React from 'react';
import { useTranslation } from 'react-i18next';
import { useTheme } from '../../themes/ThemeContext';
import type { ThemeConfig } from '../../core/types';
import { FormSelect } from '../ui/FormField';

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
  const { t } = useTranslation('common');
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
      <FormSelect
        className={`flex items-center gap-2 ${className}`}
        id="theme-selector"
        label={t('themeSelector.label')}
        labelClassName={showLabel ? 'mb-0 text-sm font-medium text-fg dark:text-fg-dark' : 'sr-only'}
        value={theme.name}
        onChange={(e) => handleThemeChange(e.target.value)}
        options={availableThemes.map((themeName) => ({
          value: themeName,
          label: themes[themeName].name || themeName,
        }))}
        selectClassName="w-auto"
      />
  );
};
