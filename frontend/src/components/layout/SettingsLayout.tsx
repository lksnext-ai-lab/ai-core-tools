import { type ReactNode } from 'react';

interface SettingsLayoutProps {
  readonly children: ReactNode;
}

function SettingsLayout({ children }: SettingsLayoutProps) {
  return (
    <div className="rounded-lg bg-white dark:bg-gray-900">
      {children}
    </div>
  );
}

export default SettingsLayout;
