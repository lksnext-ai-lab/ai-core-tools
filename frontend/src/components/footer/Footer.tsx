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
    <footer className={`bg-white border-t border-gray-200 ${className}`}>
      {children || (showVersion && <VersionFooter />)}
    </footer>
  );
};
