import { type ReactNode } from 'react';

interface SettingsLayoutProps {
  readonly children: ReactNode;
}

function SettingsLayout({ children }: SettingsLayoutProps) {
  return (
    <div >
      {children}
    </div>
  );
}

export default SettingsLayout;
