import { useState, useEffect } from 'react';
import FormActions from './FormActions';

interface SkillFormData {
  name: string;
  description: string;
  content: string;
}

interface Skill {
  skill_id: number;
  name: string;
  description: string;
  content: string;
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
    description: '',
    content: ''
  });
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isEditing = !!skill && skill.skill_id !== 0;

  // Initialize form with existing skill data
  useEffect(() => {
    if (skill) {
      setFormData({
        name: skill.name || '',
        description: skill.description || '',
        content: skill.content || ''
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
      await onSubmit(formData);
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
          placeholder="e.g., Code Review Guidelines"
          disabled={isSubmitting}
          required
        />
        <p className="mt-1 text-xs text-gray-500">
          A short, descriptive name for the skill
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
          The agent sees this description to decide when the skill is relevant
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

      {/* Info Box */}
      <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
        <div className="flex">
          <div className="flex-shrink-0">
            <span className="text-blue-400 text-xl">💡</span>
          </div>
          <div className="ml-3 text-sm text-blue-700">
            <p>
              <strong>Tip:</strong> The <strong>description</strong> helps the agent recognize when to use this skill.
              The <strong>instructions</strong> below are loaded on-demand when the skill is activated.
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
