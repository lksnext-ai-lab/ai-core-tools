import type { ReactNode } from 'react';

export interface ExpansionDetailsProps {
  readonly header: string;
  readonly children: ReactNode;
}

export function ExpansionDetails({ header, children }: Readonly<ExpansionDetailsProps>) {
  return (
    <details open className="border border-line dark:border-line-dark rounded-md overflow-hidden">
      <summary className="px-4 py-3 bg-tableCab dark:bg-tableCab-dark cursor-pointer font-medium text-fg dark:text-fg-dark select-none">
        {header}
      </summary>
      <div className="p-4 space-y-4">{children}</div>
    </details>
  );
}

export default ExpansionDetails;