import { useEffect, useState } from 'react';
import { formatDecimal, parseDecimal } from '../../utils/systemOneQuestions';

interface DecimalInputProps {
  readonly id: string;
  readonly value: number | null | undefined;
  /** undefined = empty; NaN = not a number (the validation says so). */
  readonly onChange: (value: number | undefined) => void;
  readonly className?: string;
  readonly placeholder?: string;
  readonly describedBy?: string;
}

/**
 * A decimal field that always shows a point. A `type="number"` input follows the browser language and shows
 * "0,5" in Spanish; this is a text field with a decimal keyboard, and it still accepts a comma when typed.
 * The text being typed is kept apart from the number so "0." can be typed without the point disappearing.
 */
export function DecimalInput({ id, value, onChange, className, placeholder, describedBy }: DecimalInputProps) {
  const [draft, setDraft] = useState(formatDecimal(value));

  // Follow the value when it changes from outside, never while the user is typing something that means the same.
  useEffect(() => {
    if (parseDecimal(draft) !== value && !(draft.trim() === '' && (value === undefined || value === null))) {
      setDraft(formatDecimal(value));
    }
  }, [value]);

  return (
    <input
      id={id}
      type="text"
      inputMode="decimal"
      autoComplete="off"
      className={className}
      placeholder={placeholder}
      aria-describedby={describedBy}
      value={draft}
      onChange={(e) => {
        setDraft(e.target.value);
        onChange(parseDecimal(e.target.value));
      }}
      onBlur={() => {
        const parsed = parseDecimal(draft);
        if (parsed !== undefined && Number.isFinite(parsed)) setDraft(formatDecimal(parsed));   // 0,5 -> 0.5
      }}
    />
  );
}

export default DecimalInput;
