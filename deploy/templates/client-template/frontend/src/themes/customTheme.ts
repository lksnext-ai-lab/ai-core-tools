import type { ThemeConfig } from '@lksnext/ai-core-tools-base';

export const customTheme: ThemeConfig = {
  name: 'client-custom',
  colors: {
    primary: '#10b981',    // emerald-500 - Your primary brand color
    secondary: '#8b5cf6',  // violet-500 - Your secondary brand color
    accent: '#f59e0b',     // amber-500 - Your accent color
    background: '#f9fafb', // gray-50
    surface: '#ffffff',    // white
    text: '#111827'        // gray-900
  },
  logo: '/client-logo.png',
  favicon: '/client-favicon.ico',
  customStyles: `
    /* Custom CSS variables for advanced theming */
    :root {
      --client-primary: #10b981;
      --client-secondary: #8b5cf6;
      --client-accent: #f59e0b;
    }
    
    /* Custom component styles */
    .client-card {
      background: linear-gradient(135deg, var(--client-primary)10, var(--client-secondary)10);
      border: 1px solid var(--client-primary)30;
    }
    
    .client-button {
      background: var(--client-primary);
      color: white;
      transition: all 0.2s ease;
    }
    
    .client-button:hover {
      background: var(--client-secondary);
      transform: translateY(-1px);
    }
  `
};
