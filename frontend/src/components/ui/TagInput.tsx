import { useState, useCallback } from 'react';
import { X } from 'lucide-react';

interface TagInputProps {
  readonly id?: string;
  readonly tags: string[];
  readonly onChange: (tags: string[]) => void;
  readonly maxTags?: number;
  readonly placeholder?: string;
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
}: TagInputProps) {
  const [inputValue, setInputValue] = useState('');

  const addTag = useCallback(
    (value: string) => {
      const trimmed = value.trim().toLowerCase();
      if (!trimmed) return;
      if (tags.length >= maxTags) return;
      if (tags.includes(trimmed)) return;

      onChange([...tags, trimmed]);
      setInputValue('');
    },
    [tags, maxTags, onChange],
  );

  const removeTag = useCallback(
    (index: number) => {
      onChange(tags.filter((_, i) => i !== index));
    },
    [tags, onChange],
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLInputElement>) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        addTag(inputValue);
      } else if (e.key === 'Backspace' && !inputValue && tags.length > 0) {
        removeTag(tags.length - 1);
      }
    },
    [inputValue, tags, addTag, removeTag],
  );

  const atLimit = tags.length >= maxTags;

  return (
    <div>
      <div className="flex flex-wrap items-center gap-2 p-2 border border-line-strong rounded-lg bg-surface min-h-[44px] focus-within:ring-1 focus-within:ring-ink focus-within:border-ink dark:border-line-strong-dark dark:bg-surface-dark dark:focus-within:ring-ink-dark dark:focus-within:border-ink-dark transition-all duration-200">
        {tags.map((tag, idx) => (
          <span
            key={tag}
            className="inline-flex items-center gap-1 text-xs font-medium bg-surface-hover text-fg-secondary px-2.5 py-1 rounded-full dark:bg-surface-hover-dark dark:text-fg-secondary-dark"
          >
            {tag}
            <button
              type="button"
              onClick={() => removeTag(idx)}
              className="ml-0.5 text-fg-tertiary hover:text-fg font-medium dark:text-fg-tertiary-dark dark:hover:text-fg-dark"
              aria-label={`Remove tag ${tag}`}
            >
              <X className="w-3 h-3" />
            </button>
          </span>
        ))}
        {!atLimit && (
          <input
            id={id}
            type="text"
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={tags.length === 0 ? placeholder : ''}
            className="flex-1 min-w-[120px] border-none outline-none text-sm bg-transparent text-fg placeholder:text-fg-faint dark:text-fg-dark dark:placeholder:text-fg-faint-dark py-1 px-1"
          />
        )}
      </div>
      <p className="text-xs text-fg-tertiary dark:text-fg-tertiary-dark mt-1">
        {tags.length}/{maxTags} tags
        {atLimit ? ' (maximum reached)' : ' — press Enter to add'}
      </p>
    </div>
  );
}

export default TagInput;
