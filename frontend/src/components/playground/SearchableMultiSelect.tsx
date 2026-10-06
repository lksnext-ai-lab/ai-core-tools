import { useEffect, useId, useMemo, useRef, useState } from 'react';

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
const SEARCH_DEBOUNCE_MS = 250;
const CLEAR_ROW = '';

function summarize(value: readonly string[], anyLabel: string): string {
  if (value.length === 0) return anyLabel;
  if (value.length <= 2) return value.join(', ');
  return `${value.length} selected`;
}

/**
 * Multi-select with a search box, for fields that can have hundreds of values.
 * The list floats over the surrounding layout (it never pushes content) and flips
 * upward when there is no room below. Ancestors must not clip overflow.
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
  anyLabel = '— any —',
  disabled = false,
}: Readonly<SearchableMultiSelectProps>) {
  const [isOpen, setIsOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [activeIndex, setActiveIndex] = useState(0);
  const [openUp, setOpenUp] = useState(false);
  const [remoteItems, setRemoteItems] = useState<string[] | null>(null);
  const [isSearching, setIsSearching] = useState(false);
  const [searchFailed, setSearchFailed] = useState(false);
  const searchRequestRef = useRef(0);
  const onSearchRef = useRef(onSearch);
  const canSearchRemotely = onSearch !== undefined;
  const containerRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
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
    if (isSearching) return 'Searching…';
    if (onSearch && !trimmedQuery) {
      return `Showing first ${options.length} — type to search all values`;
    }
    if (onSearch && remoteItems && remoteItems.length >= SEARCH_RESULT_LIMIT) {
      return `Showing first ${SEARCH_RESULT_LIMIT} matches — keep typing to narrow down`;
    }
    if (totalMatches > MAX_VISIBLE_OPTIONS) {
      return `Showing ${MAX_VISIBLE_OPTIONS} of ${totalMatches} — type to narrow down`;
    }
    return null;
  })();

  const optionId = (index: number) => `${listboxId}-opt-${index}`;

  useEffect(() => {
    if (!isOpen) return;
    searchRef.current?.focus();

    const handleOutsideMouseDown = (event: MouseEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleOutsideMouseDown);
    return () => document.removeEventListener('mousedown', handleOutsideMouseDown);
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
    const rect = containerRef.current?.getBoundingClientRect();
    setOpenUp(
      rect !== undefined &&
        rect.bottom + POPOVER_HEIGHT_PX > window.innerHeight &&
        rect.top > POPOVER_HEIGHT_PX,
    );
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
        close(false);
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
        className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg
                   bg-white dark:bg-gray-800 text-gray-800 dark:text-gray-100
                   focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent
                   disabled:opacity-50 disabled:cursor-not-allowed text-sm text-left transition-shadow
                   flex items-center justify-between gap-2"
      >
        <span className="truncate">{summarize(value, anyLabel)}</span>
        <svg
          className={`w-4 h-4 shrink-0 text-gray-400 transition-transform duration-200 ${
            isOpen ? 'rotate-180' : ''
          }`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
          aria-hidden="true"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {isOpen && (
        <div
          className={`absolute left-0 right-0 z-30 border border-gray-300 dark:border-gray-600 rounded-lg
                      bg-white dark:bg-gray-800 shadow-lg overflow-hidden ${
                        openUp ? 'bottom-full mb-1' : 'top-full mt-1'
                      }`}
        >
          <input
            ref={searchRef}
            type="text"
            role="combobox"
            aria-expanded="true"
            aria-controls={listboxId}
            aria-activedescendant={items.length > 0 ? optionId(activeIndex) : undefined}
            aria-label="Search values"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setActiveIndex(0);
            }}
            onKeyDown={handleSearchKeyDown}
            placeholder="Search…"
            autoComplete="off"
            className="w-full px-3 py-2 text-sm bg-transparent text-gray-800 dark:text-gray-100
                       placeholder:text-gray-400 dark:placeholder:text-gray-500
                       border-b border-gray-200 dark:border-gray-700 focus:outline-none"
          />
          <ul
            id={listboxId}
            role="listbox"
            aria-multiselectable="true"
            className="max-h-56 overflow-y-auto py-1"
          >
            {items.length === 0 && !isSearching && (
              <li className="px-3 py-2 text-sm text-gray-500 dark:text-gray-400">
                {searchFailed ? 'Search failed — try again' : 'No matches'}
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
                  onMouseEnter={() => setActiveIndex(index)}
                  className={`px-3 py-1.5 text-sm cursor-pointer flex items-center gap-2 ${
                    isActive ? 'bg-indigo-50 dark:bg-indigo-500/20' : ''
                  } ${
                    isClearRow
                      ? 'italic text-gray-500 dark:text-gray-400'
                      : 'text-gray-800 dark:text-gray-100'
                  } ${isSelected ? 'font-medium' : ''}`}
                >
                  {!isClearRow && (
                    <span
                      aria-hidden="true"
                      className={`w-4 h-4 shrink-0 rounded border flex items-center justify-center ${
                        isSelected
                          ? 'bg-indigo-500 border-indigo-500 text-white'
                          : 'border-gray-300 dark:border-gray-500'
                      }`}
                    >
                      {isSelected && (
                        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                        </svg>
                      )}
                    </span>
                  )}
                  <span className="truncate">{isClearRow ? 'Clear selection' : item}</span>
                </li>
              );
            })}
          </ul>
          {hint && (
            <p
              className="px-3 py-1.5 text-xs text-gray-500 dark:text-gray-400 border-t border-gray-200 dark:border-gray-700"
              aria-live="polite"
            >
              {hint}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

export default SearchableMultiSelect;
