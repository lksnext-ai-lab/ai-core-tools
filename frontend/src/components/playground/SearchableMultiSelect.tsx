import { useEffect, useId, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { useTranslation } from 'react-i18next';
import { Check, ChevronDown } from 'lucide-react';

interface SearchableMultiSelectProps {
  readonly id: string;
  readonly value: readonly string[];
  readonly options: readonly string[];
  readonly onChange: (values: string[]) => void;
  /** When set, `options` is only a preview: typing queries the backend through this callback. */
  readonly onSearch?: (query: string) => Promise<string[]>;
  readonly anyLabel?: string;
  readonly disabled?: boolean;
}

export const SEARCH_RESULT_LIMIT = 50;
const MAX_VISIBLE_OPTIONS = 100;
const POPOVER_HEIGHT_PX = 300;
const POPOVER_GAP_PX = 4;
const VIEWPORT_MARGIN_PX = 8;
// Search input + hint footer, i.e. everything in the popover except the list.
const POPOVER_CHROME_PX = 72;
const LIST_MAX_HEIGHT_PX = 224;
const LIST_MIN_HEIGHT_PX = 96;
// Narrow triggers (e.g. a three-column filter grid in a squeezed chat column) still get a readable list.
const POPOVER_MIN_WIDTH_PX = 240;
const SEARCH_DEBOUNCE_MS = 250;
const CLEAR_ROW = '';

interface PopoverPosition {
  readonly left: number;
  readonly width: number;
  readonly top?: number;
  readonly bottom?: number;
  readonly listMaxHeight: number;
}

function computePopoverPosition(trigger: DOMRect): PopoverPosition {
  const spaceBelow = window.innerHeight - trigger.bottom - POPOVER_GAP_PX - VIEWPORT_MARGIN_PX;
  const spaceAbove = trigger.top - POPOVER_GAP_PX - VIEWPORT_MARGIN_PX;
  const openUp = spaceBelow < POPOVER_HEIGHT_PX && spaceAbove > spaceBelow;
  const listMaxHeight = Math.max(
    LIST_MIN_HEIGHT_PX,
    Math.min(LIST_MAX_HEIGHT_PX, (openUp ? spaceAbove : spaceBelow) - POPOVER_CHROME_PX),
  );
  const width = Math.min(
    Math.max(trigger.width, POPOVER_MIN_WIDTH_PX),
    window.innerWidth - 2 * VIEWPORT_MARGIN_PX,
  );
  const left = Math.max(
    VIEWPORT_MARGIN_PX,
    Math.min(trigger.left, window.innerWidth - width - VIEWPORT_MARGIN_PX),
  );
  const base = { left, width, listMaxHeight };
  return openUp
    ? { ...base, bottom: window.innerHeight - trigger.top + POPOVER_GAP_PX }
    : { ...base, top: trigger.bottom + POPOVER_GAP_PX };
}

function summarize(value: readonly string[], anyLabel: string, selectedLabel: (count: number) => string): string {
  if (value.length === 0) return anyLabel;
  if (value.length <= 2) return value.join(', ');
  return selectedLabel(value.length);
}

/**
 * Multi-select with a search box, for fields that can have hundreds of values.
 * The list is portaled to <body> with fixed positioning, so it floats above any
 * sibling panel, stacking context or scroll container; it flips upward when there is
 * more room above, shrinks to fit the viewport and follows the trigger on scroll/resize.
 * Toggling a value keeps the list open; Escape or an outside click closes it.
 *
 * With `onSearch`, the preloaded `options` are filtered locally right away and
 * replaced by the backend's matches once they arrive (debounced, stale-safe).
 * Values selected through a search stay listed (and checked) when the query is cleared.
 */
function SearchableMultiSelect({
  id,
  value,
  options,
  onChange,
  onSearch,
  anyLabel,
  disabled = false,
}: Readonly<SearchableMultiSelectProps>) {
  const { t } = useTranslation('common');
  const resolvedAnyLabel = anyLabel ?? t('searchableMultiSelect.any');
  const [isOpen, setIsOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [activeIndex, setActiveIndex] = useState(0);
  const [position, setPosition] = useState<PopoverPosition | null>(null);
  const [remoteItems, setRemoteItems] = useState<string[] | null>(null);
  const [isSearching, setIsSearching] = useState(false);
  const [searchFailed, setSearchFailed] = useState(false);
  const searchRequestRef = useRef(0);
  const onSearchRef = useRef(onSearch);
  const canSearchRemotely = onSearch !== undefined;
  const containerRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const popoverRef = useRef<HTMLDivElement>(null);
  const listboxId = useId();

  const trimmedQuery = query.trim().toLowerCase();
  const selectedSet = useMemo(() => new Set(value), [value]);

  const { items, totalMatches } = useMemo(() => {
    let matches: readonly string[];
    if (!trimmedQuery) {
      const optionSet = new Set(options);
      matches = [...value.filter((v) => !optionSet.has(v)), ...options];
    } else if (remoteItems) {
      matches = remoteItems;
    } else {
      matches = options.filter((option) => option.toLowerCase().includes(trimmedQuery));
    }
    const visible = matches.slice(0, MAX_VISIBLE_OPTIONS);
    const showClearRow = !trimmedQuery && value.length > 0;
    return {
      items: showClearRow ? [CLEAR_ROW, ...visible] : visible,
      totalMatches: matches.length,
    };
  }, [options, value, trimmedQuery, remoteItems]);

  const hint = (() => {
    if (isSearching) return t('searchableMultiSelect.searching');
    if (onSearch && !trimmedQuery) {
      return t('searchableMultiSelect.showingFirst', { count: options.length });
    }
    if (onSearch && remoteItems && remoteItems.length >= SEARCH_RESULT_LIMIT) {
      return t('searchableMultiSelect.showingFirstMatches', { count: SEARCH_RESULT_LIMIT });
    }
    if (totalMatches > MAX_VISIBLE_OPTIONS) {
      return t('searchableMultiSelect.showingOf', { shown: MAX_VISIBLE_OPTIONS, total: totalMatches });
    }
    return null;
  })();

  const optionId = (index: number) => `${listboxId}-opt-${index}`;

  useEffect(() => {
    if (!isOpen) return;
    searchRef.current?.focus();

    const handleOutsideMouseDown = (event: MouseEvent) => {
      const target = event.target as Node;
      if (!containerRef.current?.contains(target) && !popoverRef.current?.contains(target)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleOutsideMouseDown);
    return () => document.removeEventListener('mousedown', handleOutsideMouseDown);
  }, [isOpen]);

  useLayoutEffect(() => {
    if (!isOpen) return;
    const updatePosition = () => {
      const rect = triggerRef.current?.getBoundingClientRect();
      if (rect) setPosition(computePopoverPosition(rect));
    };
    updatePosition();
    window.addEventListener('resize', updatePosition);
    window.addEventListener('scroll', updatePosition, true);
    return () => {
      window.removeEventListener('resize', updatePosition);
      window.removeEventListener('scroll', updatePosition, true);
    };
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return;
    document.getElementById(optionId(activeIndex))?.scrollIntoView({ block: 'nearest' });
  }, [isOpen, activeIndex]);

  useEffect(() => {
    if (disabled) setIsOpen(false);
  }, [disabled]);

  useEffect(() => {
    onSearchRef.current = onSearch;
  });

  useEffect(() => {
    searchRequestRef.current += 1;
    const requestId = searchRequestRef.current;
    setRemoteItems(null);
    setSearchFailed(false);

    if (!isOpen || !canSearchRemotely || !query.trim()) {
      setIsSearching(false);
      return;
    }

    setIsSearching(true);
    const timer = setTimeout(() => {
      const search = onSearchRef.current;
      if (!search) return;
      search(query.trim())
        .then((results) => {
          if (searchRequestRef.current !== requestId) return;
          setRemoteItems(results);
          setActiveIndex(0);
        })
        .catch(() => {
          if (searchRequestRef.current !== requestId) return;
          setSearchFailed(true);
        })
        .finally(() => {
          if (searchRequestRef.current === requestId) setIsSearching(false);
        });
    }, SEARCH_DEBOUNCE_MS);

    return () => clearTimeout(timer);
  }, [isOpen, canSearchRemotely, query]);

  const open = () => {
    setQuery('');
    setActiveIndex(0);
    const rect = triggerRef.current?.getBoundingClientRect();
    if (rect) setPosition(computePopoverPosition(rect));
    setIsOpen(true);
  };

  const close = (returnFocus: boolean) => {
    setIsOpen(false);
    if (returnFocus) triggerRef.current?.focus();
  };

  const activate = (item: string) => {
    if (item === CLEAR_ROW) {
      onChange([]);
      return;
    }
    onChange(selectedSet.has(item) ? value.filter((v) => v !== item) : [...value, item]);
  };

  const handleSearchKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    switch (event.key) {
      case 'ArrowDown':
        event.preventDefault();
        setActiveIndex((prev) => Math.min(prev + 1, items.length - 1));
        break;
      case 'ArrowUp':
        event.preventDefault();
        setActiveIndex((prev) => Math.max(prev - 1, 0));
        break;
      case 'Enter':
        event.preventDefault();
        if (items.length > 0) activate(items[activeIndex] ?? CLEAR_ROW);
        break;
      case 'Escape':
        event.preventDefault();
        event.stopPropagation();
        close(true);
        break;
      case 'Tab':
        // The popover lives at the end of <body>: hand focus back so Tab continues from the trigger.
        close(true);
        break;
    }
  };

  return (
    <div ref={containerRef} className="relative">
      <button
        ref={triggerRef}
        type="button"
        id={id}
        disabled={disabled}
        onClick={() => (isOpen ? close(false) : open())}
        aria-haspopup="listbox"
        aria-expanded={isOpen}
        aria-controls={isOpen ? listboxId : undefined}
        title={value.length > 0 ? value.join(', ') : undefined}
        className="flex w-full items-center justify-between gap-2 rounded-lg border border-line-strong bg-surface px-3 py-2
                   text-left text-sm text-fg focus:border-accent focus:outline-none
                   disabled:cursor-not-allowed disabled:bg-surface-hover disabled:text-fg-tertiary
                   dark:border-line-strong-dark dark:bg-surface-dark dark:text-fg-dark dark:focus:border-accent
                   dark:disabled:bg-surface-hover-dark dark:disabled:text-fg-tertiary-dark"
      >
        <span className="truncate">
          {summarize(value, resolvedAnyLabel, (count) => t('searchableMultiSelect.selectedCount', { count }))}
        </span>
        <ChevronDown
          className={`h-4 w-4 shrink-0 text-fg-tertiary transition-transform dark:text-fg-tertiary-dark ${
            isOpen ? 'rotate-180' : ''
          }`}
          aria-hidden="true"
        />
      </button>

      {isOpen && position && createPortal(
        <div
          ref={popoverRef}
          style={{
            left: position.left,
            width: position.width,
            top: position.top,
            bottom: position.bottom,
          }}
          className="fixed z-50 overflow-hidden rounded-lg border border-line bg-surface
                     shadow-[0_14px_40px_rgba(32,28,20,0.14)]
                     dark:border-line-dark dark:bg-surface-dark dark:shadow-[0_14px_40px_rgba(0,0,0,0.55)]"
        >
          <input
            ref={searchRef}
            type="text"
            role="combobox"
            aria-expanded="true"
            aria-controls={listboxId}
            aria-activedescendant={items.length > 0 ? optionId(activeIndex) : undefined}
            aria-label={t('searchableMultiSelect.searchValues')}
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setActiveIndex(0);
            }}
            onKeyDown={handleSearchKeyDown}
            placeholder={t('searchableMultiSelect.searchPlaceholder')}
            autoComplete="off"
            className="w-full border-b border-line bg-transparent px-3 py-2 text-sm text-fg
                       placeholder:text-fg-faint focus:outline-none
                       dark:border-line-dark dark:text-fg-dark dark:placeholder:text-fg-faint-dark"
          />
          <ul
            id={listboxId}
            role="listbox"
            aria-multiselectable="true"
            style={{ maxHeight: position.listMaxHeight }}
            className="overflow-y-auto py-1"
          >
            {items.length === 0 && !isSearching && (
              <li className="px-3 py-2 text-sm text-fg-tertiary dark:text-fg-tertiary-dark">
                {searchFailed ? t('searchableMultiSelect.searchFailed') : t('searchableMultiSelect.noMatches')}
              </li>
            )}
            {items.map((item, index) => {
              const isClearRow = item === CLEAR_ROW;
              const isSelected = !isClearRow && selectedSet.has(item);
              const isActive = index === activeIndex;
              return (
                <li
                  key={isClearRow ? '__clear__' : item}
                  id={optionId(index)}
                  role="option"
                  aria-selected={isSelected}
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={() => activate(item)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      activate(item);
                    }
                  }}
                  onMouseEnter={() => setActiveIndex(index)}
                  className={`flex cursor-pointer items-center gap-2 px-3 py-1.5 text-sm ${
                    isActive ? 'bg-surface-hover dark:bg-surface-hover-dark' : ''
                  } ${
                    isClearRow
                      ? 'italic text-fg-tertiary dark:text-fg-tertiary-dark'
                      : 'text-fg dark:text-fg-dark'
                  } ${isSelected ? 'font-medium' : ''}`}
                >
                  {!isClearRow && (
                    <span
                      aria-hidden="true"
                      className={`flex h-4 w-4 shrink-0 items-center justify-center rounded border ${
                        isSelected
                          ? 'border-ink bg-ink text-ink-on dark:border-ink-dark dark:bg-ink-dark dark:text-ink-on-dark'
                          : 'border-line-strong dark:border-line-strong-dark'
                      }`}
                    >
                      {isSelected && <Check className="h-3 w-3" strokeWidth={3} />}
                    </span>
                  )}
                  <span className="truncate" title={isClearRow ? undefined : item}>
                    {isClearRow ? t('searchableMultiSelect.clearSelection') : item}
                  </span>
                </li>
              );
            })}
          </ul>
          {hint && (
            <p
              className="border-t border-line px-3 py-1.5 text-xs text-fg-tertiary dark:border-line-dark dark:text-fg-tertiary-dark"
              aria-live="polite"
            >
              {hint}
            </p>
          )}
        </div>,
        document.body,
      )}
    </div>
  );
}

export default SearchableMultiSelect;
