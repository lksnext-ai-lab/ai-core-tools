import { useState, useEffect } from 'react';
import { Lightbulb } from 'lucide-react';
import FormActions from './FormActions';

interface SkillFormData {
  name: string;
  display_name: string;
  description: string;
  content: string;
  bootstrap_script_path: string;
}

interface Skill {
  skill_id: number;
  name: string;
  display_name?: string;
  description: string;
  content: string;
  bootstrap_script_path?: string | null;
  is_builtin?: boolean;
  created_at: string;
}

interface SkillFormProps {
  skill?: Skill | null;
  onSubmit: (data: SkillFormData) => Promise<void>;
  onCancel: () => void;
}

function SkillForm({ skill, onSubmit, onCancel }: Readonly<SkillFormProps>) {
  const [formData, setFormData] = useState<SkillFormData>({
    name: '',
    display_name: '',
    description: '',
    content: '',
    bootstrap_script_path: '',
  });
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isEditing = !!skill && skill.skill_id !== 0;

  // Initialize form with existing skill data
  useEffect(() => {
    if (skill) {
      setFormData({
        name: skill.name || '',
        display_name: skill.display_name || '',
        description: skill.description || '',
        content: skill.content || '',
        bootstrap_script_path: skill.bootstrap_script_path || '',
      });
    }
  }, [skill]);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    const { name, value } = e.target;
    setFormData(prev => ({
      ...prev,
      [name]: value
    }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    // Basic validation
    if (!formData.name.trim()) {
      setError('Skill name is required');
      return;
    }

    if (!formData.description.trim()) {
      setError('Skill description is required');
      return;
    }

    if (!formData.content.trim()) {
      setError('Skill content is required');
      return;
    }

    setIsSubmitting(true);
    setError(null);

    try {
      const submitData = {
        ...formData,
        bootstrap_script_path: formData.bootstrap_script_path.trim() || null,
      };
      await onSubmit(submitData as any);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save skill');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded relative">
          {error}
        </div>
      )}

      {/* Name Field */}
      <div>
        <label htmlFor="name" className="block text-sm font-medium text-gray-700 mb-1">
          Name <span className="text-red-500">*</span>
        </label>
        <input
          type="text"
          id="name"
          name="name"
          value={formData.name}
          onChange={handleChange}
          className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:ring-purple-500 focus:border-purple-500"
          placeholder="e.g., code_review_guidelines"
          disabled={isSubmitting}
          required
        />
        <p className="mt-1 text-xs text-gray-500">
          Package identifier from SKILL.md frontmatter. Use lowercase letters, numbers, and separators.
        </p>
      </div>

      {/* Display Name Field */}
      <div>
        <label htmlFor="display_name" className="block text-sm font-medium text-gray-700 mb-1">
          Display Name
        </label>
        <input
          type="text"
          id="display_name"
          name="display_name"
          value={formData.display_name}
          onChange={handleChange}
          className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:ring-purple-500 focus:border-purple-500"
          placeholder="e.g., Code Review Guidelines"
          disabled={isSubmitting}
        />
        <p className="mt-1 text-xs text-gray-500">
          Human-friendly label shown in the UI. Defaults to the name if left blank.
        </p>
      </div>

      {/* Description Field */}
      <div>
        <label htmlFor="description" className="block text-sm font-medium text-gray-700 mb-1">
          Description <span className="text-red-500">*</span>
        </label>
        <input
          type="text"
          id="description"
          name="description"
          value={formData.description}
          onChange={handleChange}
          className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:ring-purple-500 focus:border-purple-500"
          placeholder="e.g., Best practices for reviewing code quality"
          disabled={isSubmitting}
          required
        />
        <p className="mt-1 text-xs text-gray-500">
          Router metadata. Make this self-contained so the agent can decide when the skill is relevant.
        </p>
      </div>

      {/* Content Field */}
      <div>
        <label htmlFor="content" className="block text-sm font-medium text-gray-700 mb-1">
          Skill Instructions <span className="text-red-500">*</span>
        </label>
        <textarea
          id="content"
          name="content"
          value={formData.content}
          onChange={handleChange}
          rows={15}
          className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:ring-purple-500 focus:border-purple-500 font-mono text-sm"
          placeholder={`# Code Review Guidelines

## Overview
When reviewing code, follow these steps...

## Checklist
- [ ] Check for proper error handling
- [ ] Verify naming conventions
- [ ] Look for security vulnerabilities
...`}
          disabled={isSubmitting}
          required
        />
        <p className="mt-1 text-xs text-gray-500">
          Markdown-formatted instructions that will be loaded when the agent activates this skill
        </p>
      </div>

      {/* Bootstrap Path Field */}
      <div>
        <label htmlFor="bootstrap_script_path" className="block text-sm font-medium text-gray-700 mb-1">
          Bootstrap Script Path
        </label>
        <input
          type="text"
          id="bootstrap_script_path"
          name="bootstrap_script_path"
          value={formData.bootstrap_script_path}
          onChange={handleChange}
          className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:ring-purple-500 focus:border-purple-500 font-mono text-sm"
          placeholder="scripts/bootstrap.py"
          disabled={isSubmitting}
        />
        <p className="mt-1 text-xs text-gray-500">
          Optional package-root path to a reviewed script that runs after resources are copied into the sandbox.
        </p>
      </div>

      {/* Info Box */}
      <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
        <div className="flex">
          <div className="flex-shrink-0">
            <Lightbulb className="w-4 h-4 text-yellow-500" />
          </div>
          <div className="ml-3 text-sm text-blue-700">
            <p>
              <strong>Tip:</strong> The <strong>description</strong> helps the agent recognize when to use this skill.
              The <strong>instructions</strong> below are loaded on-demand when the skill is activated. Put runtime setup guidance in SKILL.md or a reviewed bootstrap script, not in a dependency registry.
            </p>
          </div>
        </div>
      </div>

      {/* Form Actions */}
      <FormActions
        onCancel={onCancel}
        isSubmitting={isSubmitting}
        isEditing={isEditing}
        submitLabel={isEditing ? 'Update Skill' : 'Create Skill'}
      />
    </form>
  );
}

export default SkillForm;
