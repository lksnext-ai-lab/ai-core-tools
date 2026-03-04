import { useState, useCallback } from 'react';

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
      <div className="flex flex-wrap items-center gap-2 p-2 border border-gray-300 rounded-xl min-h-[44px] focus-within:ring-2 focus-within:ring-blue-500 focus-within:border-blue-500 transition-all duration-200">
        {tags.map((tag, idx) => (
          <span
            key={tag}
            className="inline-flex items-center gap-1 text-sm bg-blue-100 text-blue-800 px-2.5 py-1 rounded-full"
          >
            {tag}
            <button
              type="button"
              onClick={() => removeTag(idx)}
              className="ml-0.5 text-blue-600 hover:text-blue-900 font-medium"
              aria-label={`Remove tag ${tag}`}
            >
              ×
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
            className="flex-1 min-w-[120px] border-none outline-none text-sm bg-transparent py-1 px-1"
          />
        )}
      </div>
      <p className="text-xs text-gray-500 mt-1">
        {tags.length}/{maxTags} tags
        {atLimit ? ' (maximum reached)' : ' — press Enter to add'}
      </p>
    </div>
  );
}

export default TagInput;
