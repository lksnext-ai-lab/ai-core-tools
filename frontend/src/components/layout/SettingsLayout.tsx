import { type ReactNode } from 'react';

interface SettingsLayoutProps {
  readonly children: ReactNode;
}

function SettingsLayout({ children }: SettingsLayoutProps) {
  return (
    <div className="bg-white rounded-lg">
      {children}
    </div>
  );
}

export default SettingsLayout;
