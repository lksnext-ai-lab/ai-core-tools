import type { ReactNode } from 'react';

export interface HelpRowProps {
  /** Question or topic shown in the collapsed row. */
  readonly title: string;
  readonly children: ReactNode;
  readonly className?: string;
}

/** Collapsible on-screen help, one per page, placed under the page title. Never put essential information inside. */
export function HelpRow({ title, children, className = '' }: Readonly<HelpRowProps>) {
  return (
    <details
      className={`group mb-5 max-w-[680px] rounded-md border border-bg-soft dark:border-bronze-border-dark bg-canvas-alt dark:bg-canvas-alt-dark ${className}`}
    >

      <summary
        className="flex cursor-pointer list-none items-center justify-between gap-3 rounded-md px-3.5 py-2.5 text-[13.5px] text-fg dark:text-fg-dark
                   [&::-webkit-details-marker]:hidden focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus dark:focus-visible:outline-focus-dark"
      >
        {title}
        <span
          aria-hidden="true"
          className="text-lg leading-none text-fg-tertiary transition-transform duration-150 group-open:rotate-90 motion-reduce:transition-none dark:text-fg-tertiary-dark"
        >
          ›
        </span>
      </summary>
      <div className="px-3.5 pb-3.5 text-[13px] leading-relaxed text-fg-secondary dark:text-fg-secondary-dark">
        {children}
      </div>
    </details>
  );
}

export default HelpRow;
