import React from 'react';
import { useTheme } from '@lksnext/ai-core-tools-base';

interface ClientCardProps {
  title: string;
  description: string;
  icon?: string;
  onClick?: () => void;
}

const ClientCard: React.FC<ClientCardProps> = ({ title, description, icon, onClick }) => {
  const { theme } = useTheme();

  return (
    <div
      className="p-4 rounded-lg shadow-sm border cursor-pointer hover:shadow-md transition-shadow"
      style={{
        backgroundColor: theme.colors?.surface,
        borderColor: theme.colors?.primary + '20'
      }}
      onClick={onClick}
      onKeyDown={e => {
        if (onClick && (e.key === 'Enter' || e.key === ' ')) {
          e.preventDefault();
          onClick();
        }
      }}
      tabIndex={0}
      role="button"
    >
      <div className="flex items-center space-x-3">
        {icon && (
          <div 
            className="p-2 rounded-full"
            style={{ backgroundColor: theme.colors?.primary + '20' }}
          >
            <span className="text-lg">{icon}</span>
          </div>
        )}
        <div>
          <h3 
            className="font-semibold"
            style={{ color: theme.colors?.text }}
          >
            {title}
          </h3>
          <p 
            className="text-sm opacity-75"
            style={{ color: theme.colors?.text }}
          >
            {description}
          </p>
        </div>
      </div>
    </div>
  );
};

export default ClientCard;
