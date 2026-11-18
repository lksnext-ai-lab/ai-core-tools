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
        className={`flex flex-wrap items-center gap-2 p-2 border rounded-xl min-h-[44px] transition-all duration-200 ${
          disabled
            ? 'border-gray-200 bg-gray-50 dark:border-gray-700 dark:bg-gray-800/50'
            : 'border-gray-300 focus-within:ring-2 focus-within:ring-blue-500 focus-within:border-blue-500 dark:border-gray-600'
        }`}
      >
        {tags.map((tag, idx) => (
          <span
            key={tag}
            className={`inline-flex items-center gap-1 text-sm px-2.5 py-1 rounded-full ${
              disabled
                ? 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300'
                : 'bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-200'
            }`}
          >
            {tag}
            {!disabled && (
              <button
                type="button"
                onClick={() => removeTag(idx)}
                className="ml-0.5 text-blue-600 hover:text-blue-900 font-medium dark:text-blue-300 dark:hover:text-blue-100"
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
          className="flex-1 min-w-[120px] border-none outline-none text-sm bg-transparent py-1 px-1 text-gray-900 placeholder:text-gray-400 disabled:cursor-not-allowed disabled:text-gray-600 read-only:cursor-default dark:text-gray-100 dark:placeholder:text-gray-500 dark:disabled:text-gray-300"
        />
      </div>
      <p className="text-xs text-gray-600 mt-1 dark:text-gray-300" aria-live="polite">
        {tags.length}/{maxTags} tags
        {atLimit ? ' (maximum reached)' : ' — press Enter to add'}
      </p>
    </div>
  );
}

export default TagInput;
