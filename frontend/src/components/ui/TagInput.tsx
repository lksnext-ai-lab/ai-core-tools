import { useState, useCallback } from 'react';
import { X } from 'lucide-react';

interface TagInputProps {
  readonly id?: string;
  readonly tags: string[];
  readonly onChange: (tags: string[]) => void;
  readonly maxTags?: number;
  readonly placeholder?: string;
  readonly disabled?: boolean;
}

/**
 * Tag input component — type text and press Enter to add tags as removable pills.
 */
export function TagInput({
  id,
  tags,
  onChange,
  maxTags = 5,
  placeholder = 'Type and press Enter',
  disabled = false,
}: TagInputProps) {
  const [inputValue, setInputValue] = useState('');

  const addTag = useCallback(
    (value: string) => {
      if (disabled) return;
      const trimmed = value.trim().toLowerCase();
      if (!trimmed) return;
      if (tags.length >= maxTags) return;
      if (tags.includes(trimmed)) return;

      onChange([...tags, trimmed]);
      setInputValue('');
    },
    [tags, maxTags, onChange, disabled],
  );

  const removeTag = useCallback(
    (index: number) => {
      if (disabled) return;
      onChange(tags.filter((_, i) => i !== index));
    },
    [tags, onChange, disabled],
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLInputElement>) => {
      if (disabled) return;
      if (e.key === 'Enter') {
        e.preventDefault();
        addTag(inputValue);
      } else if (e.key === 'Backspace' && !inputValue && tags.length > 0) {
        removeTag(tags.length - 1);
      }
    },
    [inputValue, tags, addTag, removeTag, disabled],
  );

  const atLimit = tags.length >= maxTags;

  return (
    <div>
      <div
        className={`flex flex-wrap items-center gap-2 p-2 border dark:border-line-strong-dark rounded-md min-h-[44px] transition-all duration-200 focus-within:border-accent focus-within:ring-1 focus-within:ring-accent ${
          disabled ? 'bg-surface-hover text-fg-tertiary cursor-not-allowed dark:bg-surface-hover-dark dark:text-fg-tertiary-dark' : ''
        }`}
      >
        {tags.map((tag, idx) => (
          <span
            key={tag}
            className={`inline-flex items-center gap-1 text-sm px-2.5 py-1 rounded-full  ${
              disabled ? 'bg-surface-hover text-fg-tertiary cursor-not-allowed dark:bg-surface-hover-dark dark:text-fg-tertiary-dark' : 'text-bronze dark:text-bronze-dark font-medium bg-bronze-bg-soft dark:bg-[var(--color-border-card-dark)]'
            }`}
          >
            {tag}
            {!disabled && (
              <button
                type="button"
                onClick={() => removeTag(idx)}
                className="ml-0.5 text-bronze dark:text-bronze-dark font-medium bg-bronze-bg-soft dark:bg-[var(--color-border-card-dark)]"
                aria-label={`Remove tag ${tag}`}
              >
                <X className="w-3 h-3" />
              </button>
            )}
          </span>
        ))}
        <input
          id={id}
          type="text"
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={tags.length === 0 && !atLimit ? placeholder : ''}
          disabled={disabled}
          readOnly={!disabled && atLimit}
          className="flex-1 min-w-[120px] border-none outline-none text-sm bg-transparent py-1 px-1 text-fg dark:text-fg-dark placeholder:text-gray-400 dark:placeholder:text-fg-faint-dark disabled:cursor-not-allowed disabled:text-fg-tertiary dark:disabled:text-fg-tertiary-dark read-only:cursor-default"
        />
      </div>
      <p className="text-xs text-fg-secondary mt-1 dark:text-fg-secondary-dark" aria-live="polite">
        {tags.length}/{maxTags} tags
        {atLimit ? ' (maximum reached)' : ' — press Enter to add'}
      </p>
    </div>
  );
}

export default TagInput;
