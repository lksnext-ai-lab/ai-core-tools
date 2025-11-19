import React from 'react';
import { useTheme } from '@lksnext/ai-core-tools-base';

interface ThemePreviewCardProps {
  theme: {
    name: string;
    colors: {
      primary: string;
      secondary: string;
      accent: string;
      background: string;
      surface: string;
      text: string;
    };
  };
  isSelected?: boolean;
  onSelect?: () => void;
  onPreview?: () => void;
}

const ThemePreviewCard: React.FC<ThemePreviewCardProps> = ({
  theme,
  isSelected = false,
  onSelect,
  onPreview
}) => {
  const { theme: currentTheme } = useTheme();

  return (
    <div
      className={`p-4 rounded-lg border-2 cursor-pointer transition-all hover:scale-105 hover:shadow-lg ${
        isSelected ? 'ring-2 ring-blue-500' : ''
      }`}
      style={{
        backgroundColor: currentTheme.colors?.surface,
        borderColor: isSelected ? '#3B82F6' : currentTheme.colors?.primary + '30'
      }}
      onClick={onSelect}
      onKeyDown={e => {
        if (onSelect && (e.key === 'Enter' || e.key === ' ')) {
          e.preventDefault();
          onSelect();
        }
      }}
      tabIndex={0}
      role="button"
    >
      {/* Theme Name */}
      <div className="mb-3">
        <h3 
          className="font-semibold text-lg"
          style={{ color: currentTheme.colors?.text }}
        >
          {theme.name}
        </h3>
      </div>
      
      {/* Color Palette Preview */}
      <div className="space-y-2 mb-4">
        <div 
          className="h-8 rounded"
          style={{ backgroundColor: theme.colors.primary }}
        />
        <div className="grid grid-cols-2 gap-1">
          <div 
            className="h-6 rounded"
            style={{ backgroundColor: theme.colors.secondary }}
          />
          <div 
            className="h-6 rounded"
            style={{ backgroundColor: theme.colors.accent }}
          />
        </div>
        <div className="grid grid-cols-2 gap-1">
          <div 
            className="h-4 rounded"
            style={{ backgroundColor: theme.colors.background }}
          />
          <div 
            className="h-4 rounded"
            style={{ backgroundColor: theme.colors.surface }}
          />
        </div>
      </div>
      
      {/* Color Values */}
      <div className="space-y-1 mb-4">
        {Object.entries(theme.colors).map(([key, value]) => (
          <div key={key} className="flex items-center justify-between text-xs">
            <span 
              className="font-medium"
              style={{ color: currentTheme.colors?.text, opacity: 0.7 }}
            >
              {key}:
            </span>
            <span 
              className="font-mono"
              style={{ color: currentTheme.colors?.text, opacity: 0.8 }}
            >
              {value}
            </span>
          </div>
        ))}
      </div>
      
      {/* Action Buttons */}
      <div className="flex space-x-2">
        <button
          className="flex-1 px-3 py-2 rounded text-sm font-medium transition-all"
          style={{
            backgroundColor: theme.colors.primary,
            color: '#ffffff'
          }}
          onClick={(e) => {
            e.stopPropagation();
            onSelect?.();
          }}
        >
          {isSelected ? 'Selected' : 'Select'}
        </button>
        <button
          className="px-3 py-2 rounded text-sm font-medium border transition-all hover:bg-gray-50"
          style={{
            borderColor: currentTheme.colors?.primary,
            color: currentTheme.colors?.primary
          }}
          onClick={(e) => {
            e.stopPropagation();
            onPreview?.();
          }}
        >
          Preview
        </button>
      </div>
    </div>
  );
};

export default ThemePreviewCard;
