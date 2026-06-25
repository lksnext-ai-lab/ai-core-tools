import { useState, useEffect, useRef, useId, useCallback } from 'react';
import { Search, X, Loader2 } from 'lucide-react';
import { adminService } from '../../services/admin';
import type { User } from '../../services/admin';
import { errorMessage } from '../../constants/messages';

export interface UserPickerProps {
  /** Label shown above the combobox input. */
  readonly label: string;
  /** The currently selected user, or null if nothing is selected. */
  readonly value: User | null;
  /** Called when the user selects a candidate from the listbox. */
  readonly onSelect: (user: User) => void;
  /** Called when the selection is cleared. */
  readonly onClear: () => void;
  /** User ID to exclude from results (typically the user being deleted). */
  readonly excludeUserId?: number;
  /** Disable the input (e.g. while a parent operation is in progress). */
  readonly disabled?: boolean;
  /** Extra id suffix used to make aria ids unique when multiple pickers coexist. */
  readonly inputId?: string;
}

const DEBOUNCE_MS = 300;
const MAX_RESULTS = 8;

function UserPicker({
  label,
  value,
  onSelect,
  onClear,
  excludeUserId,
  disabled = false,
  inputId,
}: Readonly<UserPickerProps>) {
  const uid = useId();
  const comboboxId = inputId ?? `user-picker-${uid}`;
  const listboxId = `${comboboxId}-listbox`;
  const errorId = `${comboboxId}-error`;

  const [query, setQuery] = useState('');
  const [candidates, setCandidates] = useState<User[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isOpen, setIsOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const [fetchError, setFetchError] = useState<string | null>(null);

  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Over-fetch by 2x+1 so client-side exclusion (target user + omniadmins) still yields MAX_RESULTS.
  const fetchCandidates = useCallback(
    async (search: string) => {
      setIsLoading(true);
      setFetchError(null);
      try {
        const response = await adminService.getUsers(1, MAX_RESULTS * 2 + 1, search || undefined);
        const filtered = response.users.filter(
          (u) => u.user_id !== excludeUserId && !u.is_omniadmin,
        );
        setCandidates(filtered.slice(0, MAX_RESULTS));
        setIsOpen(true);
        setActiveIndex(-1);
      } catch (err: unknown) {
        setFetchError(errorMessage(err, 'Failed to search users'));
        setCandidates([]);
      } finally {
        setIsLoading(false);
      }
    },
    [excludeUserId],
  );

  useEffect(() => {
    if (value) return; // Don't re-search while a selection is active.
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (!query.trim()) {
      setCandidates([]);
      setIsOpen(false);
      return;
    }
    debounceRef.current = setTimeout(() => {
      void fetchCandidates(query);
    }, DEBOUNCE_MS);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [query, value, fetchCandidates]);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      const target = e.target as Node;
      if (
        !inputRef.current?.closest('[data-user-picker]')?.contains(target)
      ) {
        setIsOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  function handleSelect(user: User) {
    onSelect(user);
    setQuery('');
    setCandidates([]);
    setIsOpen(false);
    setActiveIndex(-1);
  }

  function handleClear() {
    onClear();
    setQuery('');
    setCandidates([]);
    setIsOpen(false);
    setActiveIndex(-1);
    setTimeout(() => inputRef.current?.focus(), 0); // Restore focus after clear.
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Tab') {
      setIsOpen(false);
      return;
    }

    if (!isOpen || candidates.length === 0) {
      if (e.key === 'Escape') {
        e.preventDefault();
        e.stopPropagation(); // Prevent Escape from bubbling to and closing the Modal.
        setIsOpen(false);
      }
      return;
    }

    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActiveIndex((prev) => (prev < candidates.length - 1 ? prev + 1 : 0));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActiveIndex((prev) => (prev > 0 ? prev - 1 : candidates.length - 1));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (activeIndex >= 0 && activeIndex < candidates.length) {
        handleSelect(candidates[activeIndex]);
      }
    } else if (e.key === 'Escape') {
      e.preventDefault();
      e.stopPropagation(); // Prevent Escape from bubbling to and closing the Modal.
      setIsOpen(false);
      setActiveIndex(-1);
    }
  }

  useEffect(() => {
    if (activeIndex < 0 || !listRef.current) return;
    const item = listRef.current.children[activeIndex] as HTMLElement | undefined;
    item?.scrollIntoView({ block: 'nearest' });
  }, [activeIndex]);

  const activeOptionId =
    activeIndex >= 0 ? `${listboxId}-option-${activeIndex}` : undefined;

  const liveRegionText = isLoading
    ? 'Searching…'
    : candidates.length > 0
    ? `${candidates.length} results`
    : '';

  return (
    <div data-user-picker className="relative">
      <label
        htmlFor={comboboxId}
        className="block text-sm font-medium text-gray-700 dark:text-slate-300 mb-1.5"
      >
        {label}
      </label>

      {value ? (
        <div className="flex items-center gap-2 px-3 py-2 bg-blue-50 dark:bg-blue-900/30 border border-blue-300 dark:border-blue-700 rounded-lg">
          <div className="flex-1 min-w-0">
            <span className="text-sm font-medium text-gray-900 dark:text-slate-100 truncate block">
              {value.name || value.email}
            </span>
            {value.name && (
              <span className="text-xs text-gray-500 dark:text-slate-400 truncate block">
                {value.email}
              </span>
            )}
          </div>
          <button
            type="button"
            onClick={handleClear}
            disabled={disabled}
            aria-label={`Remove selected user ${value.name || value.email}`}
            className="flex-shrink-0 text-gray-400 hover:text-gray-600 dark:text-slate-400 dark:hover:text-slate-200 focus:outline-none focus:ring-2 focus:ring-blue-500 rounded disabled:opacity-50"
          >
            <X className="w-4 h-4" aria-hidden="true" />
          </button>
        </div>
      ) : (
        <div className="relative">
          <span className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
            {isLoading ? (
              <Loader2 className="w-4 h-4 text-gray-400 dark:text-slate-500 animate-spin" aria-hidden="true" />
            ) : (
              <Search className="w-4 h-4 text-gray-400 dark:text-slate-500" aria-hidden="true" />
            )}
          </span>
          <span role="status" aria-live="polite" className="sr-only">
            {liveRegionText}
          </span>
          <input
            ref={inputRef}
            id={comboboxId}
            type="text"
            role="combobox"
            aria-expanded={isOpen}
            aria-haspopup="listbox"
            aria-autocomplete="list"
            aria-controls={listboxId}
            aria-activedescendant={activeOptionId}
            aria-describedby={fetchError ? errorId : undefined}
            autoComplete="off"
            disabled={disabled}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            onFocus={() => {
              if (candidates.length > 0) setIsOpen(true);
            }}
            placeholder="Search by name or email…"
            className="w-full pl-9 pr-3 py-2 bg-white dark:bg-slate-700 border border-gray-300 dark:border-slate-600 rounded-lg text-sm text-gray-900 dark:text-slate-100 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:opacity-50 disabled:cursor-not-allowed"
          />
        </div>
      )}

      {fetchError && (
        <p id={errorId} role="alert" className="mt-1 text-xs text-red-600 dark:text-red-400">
          {fetchError}
        </p>
      )}

      {isOpen && !value && (
        <ul
          ref={listRef}
          id={listboxId}
          role="listbox"
          aria-label={label}
          className="absolute z-50 w-full mt-1 bg-white dark:bg-slate-800 border border-gray-200 dark:border-slate-600 rounded-lg shadow-lg max-h-60 overflow-y-auto focus:outline-none"
        >
          {candidates.length === 0 && !isLoading && (
            <li role="presentation" className="px-4 py-3 text-sm text-gray-500 dark:text-slate-400 select-none">
              No users found
            </li>
          )}
          {candidates.map((user, index) => {
            const isActive = index === activeIndex;
            return (
              <li
                key={user.user_id}
                id={`${listboxId}-option-${index}`}
                role="option"
                aria-selected={isActive}
                onMouseDown={(e) => {
                  e.preventDefault(); // Prevent input blur before the click registers.
                  handleSelect(user);
                }}
                onMouseEnter={() => setActiveIndex(index)}
                className={`px-4 py-2.5 cursor-pointer select-none ${
                  isActive
                    ? 'bg-blue-50 dark:bg-blue-900/40'
                    : 'hover:bg-gray-50 dark:hover:bg-slate-700/50'
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-gray-900 dark:text-slate-100 truncate">
                      {user.name || user.email}
                    </p>
                    {user.name && (
                      <p className="text-xs text-gray-500 dark:text-slate-400 truncate">
                        {user.email}
                      </p>
                    )}
                  </div>
                  {!user.is_active && (
                    <span className="flex-shrink-0 text-xs text-gray-500 dark:text-slate-400 italic">
                      inactive
                    </span>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

export default UserPicker;
