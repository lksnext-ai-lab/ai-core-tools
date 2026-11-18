import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';

import enCommon from './locales/en/common.json';
import esCommon from './locales/es/common.json';

export const supportedLanguages = ['en', 'es'] as const;

export type AppLanguage =
  (typeof supportedLanguages)[number];

export const DEFAULT_LANGUAGE: AppLanguage = 'en';

/** Each language's name written in that same language (endonym). */
export const languageNames: Record<AppLanguage, string> = {
  en: 'English',
  es: 'Español',
};

export const LANGUAGE_STORAGE_KEY = 'mattin.language';

export function isSupportedLanguage(value: unknown): value is AppLanguage {
  return typeof value === 'string' && (supportedLanguages as readonly string[]).includes(value);
}

// Storage access can throw (private mode, blocked site data) — never let it break the app.
function readStoredLanguage(): AppLanguage | null {
  try {
    const stored = localStorage.getItem(LANGUAGE_STORAGE_KEY);
    return isSupportedLanguage(stored) ? stored : null;
  } catch {
    return null;
  }
}

function storeLanguage(language: AppLanguage): void {
  try {
    localStorage.setItem(LANGUAGE_STORAGE_KEY, language);
  } catch {
    // Persistence is best-effort.
  }
}

void i18n
  .use(initReactI18next)
  .init({
    resources: {
      en: { common: enCommon },
      es: { common: esCommon },
    },
    lng: readStoredLanguage() ?? DEFAULT_LANGUAGE,
    fallbackLng: DEFAULT_LANGUAGE,
    supportedLngs: [...supportedLanguages],
    defaultNS: 'common',
    ns: ['common'],
    interpolation: {
      escapeValue: false,
    },
    react: {
      useSuspense: false,
    },
  });

// Single place that persists the choice: any successful changeLanguage() call is saved.
i18n.on('languageChanged', (language) => {
  if (!isSupportedLanguage(language)) return;
  storeLanguage(language);
  if (typeof document !== 'undefined') {
    document.documentElement.lang = language;
  }
});

if (typeof document !== 'undefined') {
  document.documentElement.lang = i18n.language;
}

export default i18n;
