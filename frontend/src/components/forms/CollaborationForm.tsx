import { useState, useEffect, useRef } from "react";
import Alert from '../ui/Alert';
import { Spinner } from '../ui/Spinner';
import { ButtonApp } from '../ui/ButtonApp';
import FormField, { FormSelect } from '../ui/FormField';
import { apiService } from '../../services/api';

interface PlatformUser {
  user_id: number;
  name: string;
  email: string;
  platform_role: string;
  is_omniadmin: boolean;
}

interface CollaborationFormProps {
  readonly onSubmit: (email: string, role: string) => Promise<void>;
  readonly loading?: boolean;
}

const ROLE_DESCRIPTIONS: Record<string, string> = {
  editor: "Can view and edit app content, agents, and settings. Cannot invite users or manage collaborators.",
  administrator: "Same as editor but can also change roles of other collaborators.",
  viewer: "Can view app content and analytics but cannot modify settings or manage collaborators.",
};

function CollaborationForm({ onSubmit, loading = false }: CollaborationFormProps) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<PlatformUser[]>([]);
  const [selectedUser, setSelectedUser] = useState<PlatformUser | null>(null);
  const [role, setRole] = useState("editor");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showDropdown, setShowDropdown] = useState(false);
  const [searching, setSearching] = useState(false);
  const [protectedUsers, setProtectedUsers] = useState<PlatformUser[]>([]);
  const [highlightedIndex, setHighlightedIndex] = useState(-1);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const optionRefs = useRef<Array<HTMLLIElement | null>>([]);
  const isInputFocusedRef = useRef(false);

  // Load protected (omniadmin) accounts once so they're visible without searching
  useEffect(() => {
    apiService.getOmniadminAccounts()
      .then(setProtectedUsers)
      .catch(() => setProtectedUsers([]));
  }, []);

  // Close dropdown on outside click
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setShowDropdown(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  // Debounced search. protectedUsers is a dependency so that when the initial
  // fetch resolves (it's always async, so it never has data on the very first
  // run), the empty-query branch re-syncs `results` — and reopens the dropdown
  // if the input was already focused before the fetch finished.
  useEffect(() => {
    if (selectedUser) return;
    if (query.length < 1) {
      setResults(protectedUsers);
      setShowDropdown(isInputFocusedRef.current && protectedUsers.length > 0);
      return;
    }

    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(async () => {
      setSearching(true);
      try {
        const users = await apiService.searchPlatformUsers(query);
        setResults(users);
        setShowDropdown(users.length > 0);
      } catch {
        setResults([]);
      } finally {
        setSearching(false);
      }
    }, 300);

    return () => { if (debounceRef.current) clearTimeout(debounceRef.current); };
  }, [query, selectedUser, protectedUsers]);

  // Reset keyboard highlight whenever the result set changes
  useEffect(() => {
    setHighlightedIndex(-1);
  }, [results]);

  // Keep the keyboard-highlighted option scrolled into view
  useEffect(() => {
    if (highlightedIndex < 0) return;
    optionRefs.current[highlightedIndex]?.scrollIntoView({ block: "nearest" });
  }, [highlightedIndex]);

  // When a viewer-platform user is selected, lock role to viewer.
  // Omniadmins are exempt: new omniadmin accounts get platform_role 'admin'
  // directly, but accounts created before that default existed may still
  // carry the old 'viewer' value, which shouldn't force a viewer-only invite.
  useEffect(() => {
    if (selectedUser?.platform_role === 'viewer' && !selectedUser?.is_omniadmin) {
      setRole('viewer');
    }
  }, [selectedUser]);

  function selectUser(user: PlatformUser) {
    setSelectedUser(user);
    setQuery(user.name ? `${user.name} (${user.email})` : user.email);
    setShowDropdown(false);
    setResults([]);
    setHighlightedIndex(-1);
  }

  function handleInputKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (!showDropdown || results.length === 0) return;

    if (e.key === "ArrowDown") {
      e.preventDefault();
      setHighlightedIndex((prev) => (prev + 1 >= results.length ? 0 : prev + 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setHighlightedIndex((prev) => (prev - 1 < 0 ? results.length - 1 : prev - 1));
    } else if (e.key === "Enter") {
      if (highlightedIndex >= 0 && highlightedIndex < results.length) {
        e.preventDefault();
        selectUser(results[highlightedIndex]);
      }
    } else if (e.key === "Escape") {
      setShowDropdown(false);
      setHighlightedIndex(-1);
    }
  }

  function clearSelection() {
    setSelectedUser(null);
    setQuery("");
    setRole("editor");
    setResults([]);
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedUser) { setError("Please select a user from the list"); return; }
    setIsSubmitting(true);
    setError(null);
    try {
      await onSubmit(selectedUser.email, role);
      clearSelection();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to send invitation");
    } finally {
      setIsSubmitting(false);
    }
  };

  const isViewerLocked = selectedUser?.platform_role === 'viewer' && !selectedUser?.is_omniadmin;

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      {error && <Alert type="error" message={error} />}

      <div className="space-y-4">
        {/* User search */}
        <div>
          <div ref={dropdownRef} className="relative">
            <div className="relative">
              <FormField
                label="User"
                id="collab-user"
                value={query}
                onChange={(e) => { setQuery(e.target.value); if (selectedUser) setSelectedUser(null); }}
                onFocus={() => {
                  isInputFocusedRef.current = true;
                  if (!selectedUser && query.length < 1 && protectedUsers.length > 0) setShowDropdown(true);
                }}
                onBlur={() => { isInputFocusedRef.current = false; }}
                onKeyDown={handleInputKeyDown}
                placeholder="Search by name or email…"
                disabled={isSubmitting || loading}
                inputClassName="pr-10"
                autoComplete="off"
                role="combobox"
                ariaExpanded={showDropdown}
                ariaControls="collab-user-listbox"
                ariaActiveDescendant={highlightedIndex >= 0 ? `collab-user-option-${results[highlightedIndex]?.user_id}` : undefined}
              />
              {searching && (
                <div className="absolute right-3 top-[calc(100%-1.1875rem)] flex -translate-y-1/2">
                  <Spinner size="sm" tone="muted" />
                </div>
              )}
              {selectedUser && (
                <button
                  type="button"
                  onClick={clearSelection}
                  aria-label="Clear selection"
                  className="absolute right-3 top-[calc(100%-1.1875rem)] -translate-y-1/2 text-gray-400 hover:text-gray-600"
                >
                  ✕
                </button>
              )}
            </div>

            {showDropdown && (
              <ul id="collab-user-listbox" role="listbox" className="absolute z-10 mt-1 w-full bg-white border border-gray-200 rounded-xl shadow-lg max-h-52 overflow-y-auto">
                {results.map((u, index) => (
                  <li
                    key={u.user_id}
                    ref={(el) => { optionRefs.current[index] = el; }}
                    id={`collab-user-option-${u.user_id}`}
                    role="option"
                    aria-selected={index === highlightedIndex}
                    className={index > 0 ? "border-t border-line dark:border-line-dark" : ""}
                  >
                    <button
                      type="button"
                      onClick={() => selectUser(u)}
                      onMouseEnter={() => setHighlightedIndex(index)}
                      className={`w-full text-left flex items-center justify-between gap-2 px-4 py-3 transition-colors ${
                        index === highlightedIndex
                          ? "bg-surface-hover dark:bg-btCard-hover"
                          : "bg-surface dark:bg-surface-dark hover:bg-surface-hover dark:hover:bg-surface-hover-dark"
                      }`}
                    >
                      <div>
                        <div className="text-sm font-medium text-gray-900">{u.name || u.email}</div>
                        {u.name && <div className="text-xs text-gray-500">{u.email}</div>}
                      </div>
                      {u.is_omniadmin && (
                        <span className="shrink-0 text-xs bg-amber-100 text-amber-700 px-2 py-0.5 rounded-full">
                          Protected · Admin
                        </span>
                      )}
                      {!u.is_omniadmin && u.platform_role === 'viewer' && (
                        <span className="shrink-0 text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full">
                          Viewer
                        </span>
                      )}
                    </button>
                  </li>
                ))}
              </ul>
            )}

            {query.length >= 1 && !searching && results.length === 0 && !selectedUser && (
              <p className="mt-1 text-sm text-gray-500">No users found matching "{query}"</p>
            )}
          </div>
        </div>

        {/* Role selector */}
        <div>
          <FormSelect
            id="collab-role"
            label="Invitation Role"
            value={role}
            onChange={(e) => setRole(e.target.value)}
            disabled={isViewerLocked || isSubmitting || loading}
            options={[
              ...(isViewerLocked ? [] : [
                { value: 'editor', label: 'Editor' },
                { value: 'administrator', label: 'Administrator' },
              ]),
              { value: 'viewer', label: 'Viewer' },
            ]}
          />
          {selectedUser?.is_omniadmin && (
            <p className="mt-1 text-sm text-amber-600">
              This is a protected admin account (configured via server settings).
            </p>
          )}
          {isViewerLocked && (
            <p className="mt-1 text-sm text-amber-600">
              This user has a Viewer platform role and can only be invited as a Viewer.
            </p>
          )}
          {!isViewerLocked && !selectedUser?.is_omniadmin && (
            <p className="mt-1 text-sm text-fg-tertiary dark:text-fg-tertiary-dark">{ROLE_DESCRIPTIONS[role]}</p>
          )}
        </div>
      </div>

      <div className="flex justify-end">
        <ButtonApp
          type="submit"
          label={isSubmitting ? "Sending…" : "Send Invitation"}
          disabled={!selectedUser || loading}
          loading={isSubmitting}
        />
      </div>
    </form>
  );
}

export default CollaborationForm;
