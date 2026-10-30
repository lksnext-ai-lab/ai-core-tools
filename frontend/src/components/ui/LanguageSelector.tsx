import React, { useEffect, useId, useLayoutEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Check, ChevronDown, Globe } from 'lucide-react';

import {
  DEFAULT_LANGUAGE,
  isSupportedLanguage,
  languageNames,
  supportedLanguages,
  type AppLanguage,
} from '../../i18n';

export interface LanguageSelectorProps {
  readonly className?: string;
}

const LanguageSelector: React.FC<LanguageSelectorProps> = ({ className = '' }) => {
  const { t, i18n } = useTranslation();
  const listboxId = useId();
  const containerRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const listboxRef = useRef<HTMLUListElement>(null);

  const [isOpen, setIsOpen] = useState(false);
  const [openUpward, setOpenUpward] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const [isChanging, setIsChanging] = useState(false);
  const [hasError, setHasError] = useState(false);

  const resolved = i18n.resolvedLanguage ?? i18n.language;
  const currentLanguage: AppLanguage = isSupportedLanguage(resolved) ? resolved : DEFAULT_LANGUAGE;
  const optionId = (language: AppLanguage) => `${listboxId}-${language}`;

  const open = () => {
    setActiveIndex(supportedLanguages.indexOf(currentLanguage));
    setIsOpen(true);
  };

  const close = (restoreFocus: boolean) => {
    setIsOpen(false);
    if (restoreFocus) triggerRef.current?.focus();
  };

  const selectLanguage = async (language: AppLanguage) => {
    close(true);
    if (language === currentLanguage) return;

    setIsChanging(true);
    setHasError(false);
    try {
      await i18n.changeLanguage(language);
    } catch (error) {
      console.error('Failed to change language', error);
      setHasError(true);
    } finally {
      setIsChanging(false);
    }
  };

  // Open towards the side with more room so it also works at the bottom of a menu.
  useLayoutEffect(() => {
    if (!isOpen || !containerRef.current || !listboxRef.current) return;
    const triggerRect = containerRef.current.getBoundingClientRect();
    const spaceBelow = window.innerHeight - triggerRect.bottom;
    setOpenUpward(spaceBelow < listboxRef.current.offsetHeight + 8 && triggerRect.top > spaceBelow);
    listboxRef.current.focus();
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return;
    const handleClickOutside = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [isOpen]);

  const handleTriggerKeyDown = (event: React.KeyboardEvent<HTMLButtonElement>) => {
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      open();
    }
  };

  const handleListboxKeyDown = (event: React.KeyboardEvent<HTMLUListElement>) => {
    const lastIndex = supportedLanguages.length - 1;
    switch (event.key) {
      case 'ArrowDown':
        event.preventDefault();
        setActiveIndex((index) => (index >= lastIndex ? 0 : index + 1));
        break;
      case 'ArrowUp':
        event.preventDefault();
        setActiveIndex((index) => (index <= 0 ? lastIndex : index - 1));
        break;
      case 'Home':
        event.preventDefault();
        setActiveIndex(0);
        break;
      case 'End':
        event.preventDefault();
        setActiveIndex(lastIndex);
        break;
      case 'Enter':
      case ' ':
        event.preventDefault();
        void selectLanguage(supportedLanguages[activeIndex]);
        break;
      case 'Escape':
        event.preventDefault();
        event.stopPropagation();
        close(true);
        break;
      case 'Tab':
        close(false);
        break;
    }
  };

  return (
    <div ref={containerRef} className={`relative inline-block text-left ${className}`}>
      <button
        ref={triggerRef}
        type="button"
        onClick={() => (isOpen ? close(false) : open())}
        onKeyDown={handleTriggerKeyDown}
        disabled={isChanging}
        aria-haspopup="listbox"
        aria-expanded={isOpen}
        aria-controls={isOpen ? listboxId : undefined}
        aria-label={`${t('language')}: ${languageNames[currentLanguage]}`}
        className="inline-flex min-h-10 w-full items-center gap-2 rounded-lg border border-line bg-surface px-3 text-sm font-medium text-fg transition-colors hover:bg-surface-hover focus:outline-none focus-visible:border-accent disabled:cursor-wait disabled:opacity-60 dark:border-line-dark dark:bg-surface-dark dark:text-fg-dark dark:hover:bg-surface-hover-dark dark:focus-visible:border-accent-dark"
      >
        <Globe className="h-4 w-4 shrink-0 text-fg-tertiary dark:text-fg-tertiary-dark" aria-hidden="true" />
        <span className="flex-1 truncate">{languageNames[currentLanguage]}</span>
        <ChevronDown
          className={`h-4 w-4 shrink-0 text-fg-tertiary transition-transform dark:text-fg-tertiary-dark ${isOpen ? 'rotate-180' : ''}`}
          aria-hidden="true"
        />
      </button>

      {isOpen && (
        <ul
          ref={listboxRef}
          id={listboxId}
          role="listbox"
          tabIndex={-1}
          aria-label={t('language')}
          aria-activedescendant={optionId(supportedLanguages[activeIndex])}
          onKeyDown={handleListboxKeyDown}
          className={`absolute left-0 z-50 min-w-full rounded-lg border border-line bg-surface p-1 shadow-[0_14px_40px_rgba(32,28,20,0.14)] focus:outline-none dark:border-line-dark dark:bg-surface-dark dark:shadow-[0_14px_40px_rgba(0,0,0,0.55)] ${
            openUpward ? 'bottom-full mb-2' : 'top-full mt-2'
          }`}
        >
          {supportedLanguages.map((language, index) => {
            const isSelected = language === currentLanguage;
            return (
              <li
                key={language}
                id={optionId(language)}
                role="option"
                lang={language}
                aria-selected={isSelected}
                onClick={() => void selectLanguage(language)}
                onMouseEnter={() => setActiveIndex(index)}
                className={`flex cursor-pointer items-center gap-2 whitespace-nowrap rounded-md px-3 py-1.5 text-sm transition-colors ${
                  index === activeIndex ? 'bg-surface-hover dark:bg-surface-hover-dark' : ''
                } ${
                  isSelected
                    ? 'font-medium text-fg dark:text-fg-dark'
                    : 'text-fg-secondary dark:text-fg-secondary-dark'
                }`}
              >
                <span className="flex-1">{languageNames[language]}</span>
                <Check
                  className={`h-4 w-4 shrink-0 text-accent dark:text-accent-dark ${isSelected ? '' : 'invisible'}`}
                  aria-hidden="true"
                />
              </li>
            );
          })}
        </ul>
      )}

      {hasError && (
        <p role="alert" className="mt-1 text-xs text-error dark:text-error-dark">
          {t('languageChangeError')}
        </p>
      )}
    </div>
  );
};

export default LanguageSelector;
