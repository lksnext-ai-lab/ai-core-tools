import React, { useState } from 'react';
import { useTheme } from '@lksnext/ai-core-tools-base';

interface ConfigCodeBlockProps {
  title: string;
  code: string;
  language?: string;
  showCopyButton?: boolean;
  showDownloadButton?: boolean;
  maxHeight?: string;
}

const ConfigCodeBlock: React.FC<ConfigCodeBlockProps> = ({
  title,
  code,
  language = 'typescript',
  showCopyButton = true,
  showDownloadButton = true,
  maxHeight = '400px'
}) => {
  const { theme } = useTheme();
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error('Failed to copy code:', err);
    }
  };

  const handleDownload = () => {
    const blob = new Blob([code], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${title.toLowerCase().replace(/\s+/g, '-')}.${language === 'typescript' ? 'ts' : 'js'}`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const getLanguageIcon = () => {
    switch (language) {
      case 'typescript':
        return '📘';
      case 'javascript':
        return '📜';
      case 'json':
        return '📋';
      case 'css':
        return '🎨';
      case 'html':
        return '🌐';
      default:
        return '💻';
    }
  };

  const getLanguageColor = () => {
    switch (language) {
      case 'typescript':
        return '#3178C6';
      case 'javascript':
        return '#F7DF1E';
      case 'json':
        return '#000000';
      case 'css':
        return '#1572B6';
      case 'html':
        return '#E34F26';
      default:
        return theme.colors?.primary;
    }
  };

  return (
    <div 
      className="rounded-lg shadow-lg overflow-hidden"
      style={{
        backgroundColor: theme.colors?.surface,
        border: `1px solid ${theme.colors?.primary}20`
      }}
    >
      {/* Header */}
      <div 
        className="px-4 py-3 border-b flex items-center justify-between"
        style={{
          backgroundColor: theme.colors?.primary + '10',
          borderColor: theme.colors?.primary + '20'
        }}
      >
        <div className="flex items-center space-x-2">
          <span className="text-lg">{getLanguageIcon()}</span>
          <h3 
            className="font-semibold"
            style={{ color: theme.colors?.text }}
          >
            {title}
          </h3>
          <span 
            className="px-2 py-1 rounded text-xs font-medium"
            style={{
              backgroundColor: getLanguageColor() + '20',
              color: getLanguageColor()
            }}
          >
            {language.toUpperCase()}
          </span>
        </div>
        
        <div className="flex items-center space-x-2">
          {showCopyButton && (
            <button
              onClick={handleCopy}
              className="px-3 py-1 rounded text-sm font-medium transition-all hover:scale-105"
              style={{
                backgroundColor: copied ? '#10B981' : theme.colors?.primary,
                color: '#ffffff'
              }}
            >
              {copied ? '✓ Copied!' : '📋 Copy'}
            </button>
          )}
          
          {showDownloadButton && (
            <button
              onClick={handleDownload}
              className="px-3 py-1 rounded text-sm font-medium border transition-all hover:scale-105"
              style={{
                borderColor: theme.colors?.secondary,
                color: theme.colors?.secondary
              }}
            >
              💾 Download
            </button>
          )}
        </div>
      </div>
      
      {/* Code Content */}
      <div 
        className="relative"
        style={{ maxHeight }}
      >
        <pre 
          className="text-xs p-4 overflow-x-auto overflow-y-auto"
          style={{ 
            fontFamily: 'Monaco, Consolas, "Courier New", monospace',
            backgroundColor: '#1E1E1E',
            color: '#D4D4D4',
            maxHeight
          }}
        >
          <code>{code}</code>
        </pre>
        
        {/* Scroll Indicator */}
        <div 
          className="absolute bottom-0 right-0 left-0 h-8 bg-gradient-to-t from-gray-900 to-transparent pointer-events-none"
          style={{ display: maxHeight !== 'none' ? 'block' : 'none' }}
        />
      </div>
      
      {/* Footer */}
      <div 
        className="px-4 py-2 text-xs"
        style={{
          backgroundColor: theme.colors?.primary + '05',
          color: theme.colors?.text,
          opacity: 0.7
        }}
      >
        <div className="flex items-center justify-between">
          <span>
            {code.split('\n').length} lines • {code.length} characters
          </span>
          <span>
            {language === 'typescript' ? 'TypeScript' : language.toUpperCase()}
          </span>
        </div>
      </div>
    </div>
  );
};

export default ConfigCodeBlock;
