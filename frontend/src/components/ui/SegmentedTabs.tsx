import { useRef, type KeyboardEvent } from 'react';

export interface SegmentedTab<T extends string = string> {
  readonly id: T;
  readonly label: string;
}

export interface SegmentedTabsProps<T extends string = string> {
  readonly tabs: readonly SegmentedTab<T>[];
  readonly activeTab: T;
  readonly onChange: (tabId: T) => void;
  readonly ariaLabel: string;
  readonly className?: string;
}

/** Compact segmented tab selector for switching between related views. */
export function SegmentedTabs<T extends string>({
  tabs,
  activeTab,
  onChange,
  ariaLabel,
  className = '',
}: Readonly<SegmentedTabsProps<T>>) {
  const buttonRefs = useRef<Array<HTMLButtonElement | null>>([]);

  function handleKeyDown(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    let nextIndex: number | undefined;
    if (event.key === 'ArrowRight') nextIndex = (index + 1) % tabs.length;
    if (event.key === 'ArrowLeft') nextIndex = (index - 1 + tabs.length) % tabs.length;
    if (event.key === 'Home') nextIndex = 0;
    if (event.key === 'End') nextIndex = tabs.length - 1;
    if (nextIndex === undefined || tabs.length === 0) return;

    event.preventDefault();
    const nextTab = tabs[nextIndex];
    if (!nextTab) return;
    onChange(nextTab.id);
    buttonRefs.current[nextIndex]?.focus();
  }

  return (
    <div
      role="tablist"
      aria-label={ariaLabel}
      className={`flex w-full rounded-lg border border-line bg-surface-hover p-0.5 dark:border-transparent dark:bg-surface-hover-dark ${className}`}
    >
      {tabs.map((tab, index) => {
        const selected = tab.id === activeTab;
        return (
          <button
            key={tab.id}
            ref={(element) => { buttonRefs.current[index] = element; }}
            type="button"
            role="tab"
            aria-selected={selected}
            tabIndex={selected ? 0 : -1}
            onClick={() => onChange(tab.id)}
            onKeyDown={(event) => handleKeyDown(event, index)}
            className={`min-w-0 flex-1 rounded-md border px-1 py-1.5 text-center text-sm font-medium transition-colors ${
              selected
                ? 'border-line-strong bg-surface text-fg shadow-sm dark:border-line-strong-dark dark:bg-surface-dark dark:text-fg-dark'
                : 'border-transparent text-fg-tertiary hover:text-fg dark:bg-transparent dark:text-fg-tertiary-dark dark:hover:text-fg-dark'
            }`}
          >
            {tab.label}
          </button>
        );
      })}
    </div>
  );
}

export default SegmentedTabs;
