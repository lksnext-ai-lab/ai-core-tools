import { useId, useState, type ReactNode } from 'react';
import { ChevronDown } from 'lucide-react';

export interface ExpansionDetailsProps {
  readonly header: ReactNode;
  readonly headerExtra?: ReactNode;
  readonly children: ReactNode;
}

/** Collapsible section used to group related content, e.g. in CrawlPolicyForm. */
export function ExpansionDetails({ header, headerExtra, children }: Readonly<ExpansionDetailsProps>) {
  const [isOpen, setIsOpen] = useState(true);
  const contentId = useId();

  return (
    <div className="overflow-hidden rounded-md border border-line dark:border-line-dark">
      <div className="flex items-center gap-3 bg-tableCab px-4 py-3 dark:bg-tableCab-dark">
        <button
          type="button"
          aria-expanded={isOpen}
          aria-controls={contentId}
          onClick={() => setIsOpen(open => !open)}
          className="min-w-0 flex-1 text-left font-medium text-fg dark:text-fg-dark"
        >
          {header}
        </button>
        {headerExtra}
        <button
          type="button"
          aria-label={isOpen ? 'Contraer detalles' : 'Expandir detalles'}
          aria-expanded={isOpen}
          aria-controls={contentId}
          onClick={() => setIsOpen(open => !open)}
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md text-fg hover:bg-surface-hover dark:text-fg-dark dark:hover:bg-surface-hover-dark"
        >
          <ChevronDown
            className={`h-4 w-4 shrink-0 transition-transform ${isOpen ? 'rotate-180' : ''}`}
            aria-hidden="true"
          />
        </button>
      </div>
      <div
        id={contentId}
        hidden={!isOpen}
        className="space-y-4 border-t border-line p-4 dark:border-line-dark"
      >
        {children}
      </div>
    </div>
  );
}

export default ExpansionDetails;
