import type { Meta, StoryObj } from '@storybook/react-vite';
import { useTranslation } from 'react-i18next';

import i18n, { LANGUAGE_STORAGE_KEY, isSupportedLanguage } from '../../i18n';
import LanguageSelector from './LanguageSelector';

function TranslationPreview() {
  const { t } = useTranslation();

  return (
    <p className="text-xs text-fg-tertiary dark:text-fg-tertiary-dark">
      {t('save')} · {t('cancel')} · {t('edit')} · {t('delete')}
    </p>
  );
}

const meta = {
  title: 'UI/LanguageSelector',
  component: LanguageSelector,
  parameters: {
    layout: 'centered',
  },
  tags: ['autodocs'],
  // Snapshot the real preference and active language, apply the story's language,
  // and put everything back when the story unmounts.
  beforeEach: async ({ parameters }) => {
    let storedPreference: string | null = null;
    try {
      storedPreference = localStorage.getItem(LANGUAGE_STORAGE_KEY);
    } catch {
      // Storage unavailable — nothing to restore.
    }
    const previousLanguage = i18n.language;

    if (isSupportedLanguage(parameters.language)) {
      await i18n.changeLanguage(parameters.language);
    }

    return async () => {
      await i18n.changeLanguage(previousLanguage);
      try {
        if (storedPreference === null) {
          localStorage.removeItem(LANGUAGE_STORAGE_KEY);
        } else {
          localStorage.setItem(LANGUAGE_STORAGE_KEY, storedPreference);
        }
      } catch {
        // Storage unavailable — nothing to restore.
      }
    };
  },
  decorators: [
    (Story) => (
      <div className="flex min-h-[200px] w-56 flex-col gap-3 pt-4">
        <Story />
        <TranslationPreview />
      </div>
    ),
  ],
} satisfies Meta<typeof LanguageSelector>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

export const English: Story = {
  parameters: { language: 'en' },
};

export const Spanish: Story = {
  parameters: { language: 'es' },
};
