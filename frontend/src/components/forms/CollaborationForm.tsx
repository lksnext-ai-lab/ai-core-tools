import { useState } from "react";
import { FormField } from '../ui/FormField';
import { FormError } from '../ui/FormError';

interface CollaborationFormProps {
  readonly onSubmit: (email: string, role: string) => Promise<void>;
  readonly loading?: boolean;
}

function CollaborationForm({
  onSubmit,
  loading = false,
}: CollaborationFormProps) {
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("editor");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!email.trim()) {
      setError("Email is required");
      return;
    }

    const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailPattern.test(email)) {
      setError("Please enter a valid email address");
      return;
    }

    setIsSubmitting(true);
    setError(null);

    try {
      await onSubmit(email.trim(), role);

      // Reset form on success
      setEmail("");
      setRole("editor");
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to send invitation"
      );
    } finally {
      setIsSubmitting(false);
    }
  };


  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      {/* Error Message */}
      <FormError error={error} />

      <div className="space-y-4">
        {/* Email Input */}
        <FormField
          label="Email Address"
          id="email"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="user@example.com"
          disabled={isSubmitting || loading}
          required
        />

        <div>
          <label
            htmlFor="role"
            className="block text-sm font-medium text-gray-700 mb-2"
          >
            Invitation Role
          </label>
          <select
            id="type"
            value={role}
            onChange={(e) => setRole(e.target.value)}
            className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all duration-200"
          >
            <option value="editor">Editor</option>
            <option value="administrator">Administrador</option>
          </select>
          <div className="text-sm text-gray-600 mt-2">
            {role === "editor"
              ? "Editors can view and edit app content, agents, and settings. They cannot invite other users or manage collaborators."
              : "Administrators have same benefits as owners but can change the role of other collaborators."}
          </div>
        </div>


      </div>

      {/* Submit Button */}
      <div className="flex justify-end">
        <button
          type="submit"
          disabled={isSubmitting || loading}
          className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-400 text-white rounded-lg flex items-center transition-colors"
        >
          {isSubmitting && (
            <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
          )}
          {isSubmitting ? "Sending..." : "Send Invitation"}
        </button>
      </div>
    </form>
  );
}

export default CollaborationForm;
