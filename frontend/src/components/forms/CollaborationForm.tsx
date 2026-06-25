import { useState, useEffect, useRef } from "react";
import { FormError } from '../ui/FormError';
import { apiService } from '../../services/api';

interface PlatformUser {
  user_id: number;
  name: string;
  email: string;
  platform_role: string;
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
  const dropdownRef = useRef<HTMLDivElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

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

  // Debounced search
  useEffect(() => {
    if (selectedUser) return;
    if (query.length < 2) { setResults([]); setShowDropdown(false); return; }

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
  }, [query, selectedUser]);

  // When a viewer-platform user is selected, lock role to viewer
  useEffect(() => {
    if (selectedUser?.platform_role === 'viewer') {
      setRole('viewer');
    }
  }, [selectedUser]);

  function selectUser(user: PlatformUser) {
    setSelectedUser(user);
    setQuery(user.name ? `${user.name} (${user.email})` : user.email);
    setShowDropdown(false);
    setResults([]);
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

  const isViewerLocked = selectedUser?.platform_role === 'viewer';

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <FormError error={error} />

      <div className="space-y-4">
        {/* User search */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            User
          </label>
          <div ref={dropdownRef} className="relative">
            <div className="relative">
              <input
                type="text"
                value={query}
                onChange={(e) => { setQuery(e.target.value); if (selectedUser) setSelectedUser(null); }}
                placeholder="Search by name or email…"
                disabled={isSubmitting || loading}
                className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all duration-200 pr-10"
                autoComplete="off"
              />
              {searching && (
                <div className="absolute right-3 top-1/2 -translate-y-1/2">
                  <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-blue-500" />
                </div>
              )}
              {selectedUser && (
                <button
                  type="button"
                  onClick={clearSelection}
                  aria-label="Clear selection"
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
                >
                  ✕
                </button>
              )}
            </div>

            {showDropdown && (
              <ul className="absolute z-10 mt-1 w-full bg-white border border-gray-200 rounded-xl shadow-lg max-h-52 overflow-y-auto">
                {results.map((u) => (
                  <li key={u.user_id}>
                    <button
                      type="button"
                      onClick={() => selectUser(u)}
                      className="w-full text-left px-4 py-2.5 hover:bg-blue-50 flex items-center justify-between gap-2"
                    >
                      <div>
                        <div className="text-sm font-medium text-gray-900">{u.name || u.email}</div>
                        {u.name && <div className="text-xs text-gray-500">{u.email}</div>}
                      </div>
                      {u.platform_role === 'viewer' && (
                        <span className="shrink-0 text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full">
                          Viewer
                        </span>
                      )}
                    </button>
                  </li>
                ))}
              </ul>
            )}

            {query.length >= 2 && !searching && results.length === 0 && !selectedUser && (
              <p className="mt-1 text-sm text-gray-500">No users found matching "{query}"</p>
            )}
          </div>
        </div>

        {/* Role selector */}
        <div>
          <label htmlFor="collab-role" className="block text-sm font-medium text-gray-700 mb-2">
            Invitation Role
          </label>
          <select
            id="collab-role"
            value={role}
            onChange={(e) => setRole(e.target.value)}
            disabled={isViewerLocked || isSubmitting || loading}
            className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all duration-200 disabled:bg-gray-50 disabled:text-gray-500"
          >
            {!isViewerLocked && <option value="editor">Editor</option>}
            {!isViewerLocked && <option value="administrator">Administrator</option>}
            <option value="viewer">Viewer</option>
          </select>
          {isViewerLocked && (
            <p className="mt-1 text-sm text-amber-600">
              This user has a Viewer platform role and can only be invited as a Viewer.
            </p>
          )}
          {!isViewerLocked && (
            <p className="mt-1 text-sm text-gray-600">{ROLE_DESCRIPTIONS[role]}</p>
          )}
        </div>
      </div>

      <div className="flex justify-end">
        <button
          type="submit"
          disabled={!selectedUser || isSubmitting || loading}
          className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-400 text-white rounded-lg flex items-center transition-colors"
        >
          {isSubmitting && (
            <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2" />
          )}
          {isSubmitting ? "Sending…" : "Send Invitation"}
        </button>
      </div>
    </form>
  );
}

export default CollaborationForm;
