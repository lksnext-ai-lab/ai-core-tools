import type { ThemeConfig } from '@lksnext/ai-core-tools-base';

/**
 * Comprehensive collection of theme examples for the AI-Core-Tools library
 * These themes demonstrate various color schemes and design patterns
 */

// Corporate Themes
export const corporateBlue: ThemeConfig = {
  name: 'corporate-blue',
  colors: {
    primary: '#1e40af',    // blue-800
    secondary: '#dc2626',  // red-600
    accent: '#059669',     // emerald-600
    background: '#f8fafc', // slate-50
    surface: '#ffffff',    // white
    text: '#0f172a'        // slate-900
  },
  logo: '/mattin-small.png',
  favicon: '/favicon.ico'
};

export const corporateGreen: ThemeConfig = {
  name: 'corporate-green',
  colors: {
    primary: '#059669',    // emerald-600
    secondary: '#dc2626',  // red-600
    accent: '#7c3aed',     // violet-600
    background: '#f0fdf4', // green-50
    surface: '#ffffff',    // white
    text: '#064e3b'        // emerald-900
  },
  logo: '/corporate-logo.png',
  favicon: '/corporate-favicon.ico'
};

export const corporatePurple: ThemeConfig = {
  name: 'corporate-purple',
  colors: {
    primary: '#7c3aed',    // violet-600
    secondary: '#dc2626',  // red-600
    accent: '#059669',     // emerald-600
    background: '#faf5ff', // violet-50
    surface: '#ffffff',    // white
    text: '#581c87'        // violet-900
  },
  logo: '/corporate-logo.png',
  favicon: '/corporate-favicon.ico'
};

// Modern Themes
export const modernDark: ThemeConfig = {
  name: 'modern-dark',
  colors: {
    primary: '#3b82f6',    // blue-500
    secondary: '#8b5cf6',  // violet-500
    accent: '#f59e0b',     // amber-500
    background: '#0f172a', // slate-900
    surface: '#1e293b',    // slate-800
    text: '#f1f5f9'        // slate-100
  },
  logo: '/modern-logo.png',
  favicon: '/modern-favicon.ico'
};

export const modernLight: ThemeConfig = {
  name: 'modern-light',
  colors: {
    primary: '#3b82f6',    // blue-500
    secondary: '#8b5cf6',  // violet-500
    accent: '#f59e0b',     // amber-500
    background: '#ffffff', // white
    surface: '#f8fafc',    // slate-50
    text: '#1e293b'        // slate-800
  },
  logo: '/modern-logo.png',
  favicon: '/modern-favicon.ico'
};

// Nature Themes
export const forestGreen: ThemeConfig = {
  name: 'forest-green',
  colors: {
    primary: '#16a34a',    // green-600
    secondary: '#ea580c',  // orange-600
    accent: '#0891b2',     // cyan-600
    background: '#f0fdf4', // green-50
    surface: '#ffffff',    // white
    text: '#14532d'        // green-900
  },
  logo: '/nature-logo.png',
  favicon: '/nature-favicon.ico'
};

export const oceanBlue: ThemeConfig = {
  name: 'ocean-blue',
  colors: {
    primary: '#0ea5e9',    // sky-500
    secondary: '#06b6d4',  // cyan-500
    accent: '#f59e0b',     // amber-500
    background: '#f0f9ff', // sky-50
    surface: '#ffffff',    // white
    text: '#0c4a6e'        // sky-900
  },
  logo: '/ocean-logo.png',
  favicon: '/ocean-favicon.ico'
};

export const sunsetOrange: ThemeConfig = {
  name: 'sunset-orange',
  colors: {
    primary: '#f97316',    // orange-500
    secondary: '#ef4444',  // red-500
    accent: '#8b5cf6',     // violet-500
    background: '#fff7ed', // orange-50
    surface: '#ffffff',    // white
    text: '#9a3412'        // orange-900
  },
  logo: '/sunset-logo.png',
  favicon: '/sunset-favicon.ico'
};

// Tech Themes
export const techPurple: ThemeConfig = {
  name: 'tech-purple',
  colors: {
    primary: '#8b5cf6',    // violet-500
    secondary: '#06b6d4',  // cyan-500
    accent: '#f59e0b',     // amber-500
    background: '#faf5ff', // violet-50
    surface: '#ffffff',    // white
    text: '#581c87'        // violet-900
  },
  logo: '/tech-logo.png',
  favicon: '/tech-favicon.ico'
};

export const techCyan: ThemeConfig = {
  name: 'tech-cyan',
  colors: {
    primary: '#06b6d4',    // cyan-500
    secondary: '#8b5cf6',  // violet-500
    accent: '#f59e0b',     // amber-500
    background: '#ecfeff', // cyan-50
    surface: '#ffffff',    // white
    text: '#164e63'        // cyan-900
  },
  logo: '/tech-logo.png',
  favicon: '/tech-favicon.ico'
};

// Minimalist Themes
export const minimalistGray: ThemeConfig = {
  name: 'minimalist-gray',
  colors: {
    primary: '#6b7280',    // gray-500
    secondary: '#374151',  // gray-700
    accent: '#3b82f6',     // blue-500
    background: '#ffffff', // white
    surface: '#f9fafb',    // gray-50
    text: '#111827'        // gray-900
  },
  logo: '/minimalist-logo.png',
  favicon: '/minimalist-favicon.ico'
};

export const minimalistBlack: ThemeConfig = {
  name: 'minimalist-black',
  colors: {
    primary: '#000000',    // black
    secondary: '#6b7280',  // gray-500
    accent: '#3b82f6',     // blue-500
    background: '#ffffff', // white
    surface: '#f9fafb',    // gray-50
    text: '#000000'        // black
  },
  logo: '/minimalist-logo.png',
  favicon: '/minimalist-favicon.ico'
};

// Vibrant Themes
export const vibrantRainbow: ThemeConfig = {
  name: 'vibrant-rainbow',
  colors: {
    primary: '#ef4444',    // red-500
    secondary: '#f59e0b',  // amber-500
    accent: '#8b5cf6',     // violet-500
    background: '#fef2f2', // red-50
    surface: '#ffffff',    // white
    text: '#7f1d1d'        // red-900
  },
  logo: '/vibrant-logo.png',
  favicon: '/vibrant-favicon.ico'
};

export const vibrantNeon: ThemeConfig = {
  name: 'vibrant-neon',
  colors: {
    primary: '#10b981',    // emerald-500
    secondary: '#f59e0b',  // amber-500
    accent: '#ef4444',     // red-500
    background: '#ecfdf5', // emerald-50
    surface: '#ffffff',    // white
    text: '#064e3b'        // emerald-900
  },
  logo: '/neon-logo.png',
  favicon: '/neon-favicon.ico'
};

// Professional Themes
export const professionalBlue: ThemeConfig = {
  name: 'professional-blue',
  colors: {
    primary: '#1e40af',    // blue-800
    secondary: '#374151',  // gray-700
    accent: '#059669',     // emerald-600
    background: '#f8fafc', // slate-50
    surface: '#ffffff',    // white
    text: '#0f172a'        // slate-900
  },
  logo: '/professional-logo.png',
  favicon: '/professional-favicon.ico'
};

export const professionalGreen: ThemeConfig = {
  name: 'professional-green',
  colors: {
    primary: '#059669',    // emerald-600
    secondary: '#374151',  // gray-700
    accent: '#dc2626',     // red-600
    background: '#f0fdf4', // green-50
    surface: '#ffffff',    // white
    text: '#064e3b'        // emerald-900
  },
  logo: '/professional-logo.png',
  favicon: '/professional-favicon.ico'
};

// All themes collection
export const allThemes: Record<string, ThemeConfig> = {
  'corporate-blue': corporateBlue,
  'corporate-green': corporateGreen,
  'corporate-purple': corporatePurple,
  'modern-dark': modernDark,
  'modern-light': modernLight,
  'forest-green': forestGreen,
  'ocean-blue': oceanBlue,
  'sunset-orange': sunsetOrange,
  'tech-purple': techPurple,
  'tech-cyan': techCyan,
  'minimalist-gray': minimalistGray,
  'minimalist-black': minimalistBlack,
  'vibrant-rainbow': vibrantRainbow,
  'vibrant-neon': vibrantNeon,
  'professional-blue': professionalBlue,
  'professional-green': professionalGreen
};

// Theme categories for organization
export const themeCategories = {
  corporate: ['corporate-blue', 'corporate-green', 'corporate-purple'],
  modern: ['modern-dark', 'modern-light'],
  nature: ['forest-green', 'ocean-blue', 'sunset-orange'],
  tech: ['tech-purple', 'tech-cyan'],
  minimalist: ['minimalist-gray', 'minimalist-black'],
  vibrant: ['vibrant-rainbow', 'vibrant-neon'],
  professional: ['professional-blue', 'professional-green']
};

// Helper function to get themes by category
export const getThemesByCategory = (category: keyof typeof themeCategories): ThemeConfig[] => {
  return themeCategories[category].map(themeName => allThemes[themeName]);
};

// Helper function to get random theme
export const getRandomTheme = (): ThemeConfig => {
  const themeNames = Object.keys(allThemes);
  const randomName = themeNames[Math.floor(Math.random() * themeNames.length)];
  return allThemes[randomName];
};

// Helper function to generate theme from primary color
export const generateThemeFromPrimary = (primaryColor: string, name: string): ThemeConfig => {
  // Simple color generation - in a real app, you'd use a color library
  const colors = {
    primary: primaryColor,
    secondary: '#6b7280', // gray-500
    accent: '#f59e0b',    // amber-500
    background: '#ffffff', // white
    surface: '#f9fafb',   // gray-50
    text: '#111827'       // gray-900
  };
  
  return {
    name,
    colors,
    logo: '/generated-logo.png',
    favicon: '/generated-favicon.ico'
  };
};
