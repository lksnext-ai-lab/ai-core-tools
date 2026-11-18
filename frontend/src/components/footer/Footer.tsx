import React from 'react';
import VersionFooter from '../ui/VersionFooter';

interface FooterProps {
  className?: string;
  children?: React.ReactNode;
  showVersion?: boolean;
}

export const Footer: React.FC<FooterProps> = ({ 
  className = "",
  children,
  showVersion = true 
}) => {
  return (
    <footer className={`bg-surface border-t border-line dark:bg-surface-dark dark:border-line-dark ${className}`}>
      {children || (showVersion && <VersionFooter />)}
    </footer>
  );
};
