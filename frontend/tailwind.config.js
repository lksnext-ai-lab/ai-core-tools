/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      // Mattin AI v3 design tokens (Claude Design "Mattin AI.dc.html").
      // DEFAULT = light theme; `dark` = value to pair with the `dark:` variant.
      colors: {
        canvas: { DEFAULT: '#ffffff', alt: '#fbfaf8', dark: '#15130f', 'alt-dark': '#1b1911' },
        surface: {
          DEFAULT: '#ffffff', tint: '#faf9f7', hover: '#f5f5f5', ash: '#efefef',
          dark: '#1f1d17', 'tint-dark': '#252217', 'hover-dark': '#2a271c',
        },
        line: { DEFAULT: '#e8e8e8', strong: '#d0d0d0', dark: '#3a362a', 'strong-dark': '#4a4636' },
        ink: { DEFAULT: '#202020', on: '#ffffff', dark: '#f2efe9', 'on-dark': '#15130f' },
        fg: {
          DEFAULT: '#202020', secondary: '#4d4d4d', tertiary: '#828282', faint: '#a0a0a0', faint2: '#c8c8c8',
          dark: '#f2efe9', 'secondary-dark': '#c9c4b6', 'tertiary-dark': '#9d978a', 'faint-dark': '#8f8977', 'faint2-dark': '#5c5748',
        },
        accent: { DEFAULT: '#ff682c', dark: '#ff8452' },
        bronze: {
          DEFAULT: '#816729', strong: '#6b571f', bg: '#f3ece0', 'bg-soft': '#ebe6dd', border: '#e6ddcb',
          dark: '#c9a45c', 'strong-dark': '#e0bd7c', 'bg-dark': '#2a271c', 'bg-soft-dark': '#241f10', 'border-dark': '#4a3d1f',
        },
        success: {
          DEFAULT: '#1f7a4d', strong: '#1f6a45', bg: '#eaf5ef', border: '#cfe6da',
          dark: '#5fd99b', 'strong-dark': '#8be6b8', 'bg-dark': '#132a1e', 'border-dark': '#25493a',
        },
        error: {
          DEFAULT: '#b23b2e', strong: '#7a2d23', bg: '#fbf1ef', border: '#e8c4bd',
          dark: '#ff9686', 'strong-dark': '#ffb3a6', 'bg-dark': '#2c1815', 'border-dark': '#5c2e28',
        },
        info: {
          DEFAULT: '#3a5573', strong: '#3a6ea5', bg: '#eef4fb', border: '#d7e4f2',
          dark: '#8fb8dd', 'strong-dark': '#b7d4ee', 'bg-dark': '#16232f', 'border-dark': '#33475c',
        },
        focus: { DEFAULT: '#1a5fd6', dark: '#7fb3ff' },
        btCard: { DEFAULT: '#E8E8E8', bg: '#ffffff', border: '#e8e8e8', hover: '#212121', dark: '#2a271c', 'bg-dark': '#2a271c','border-dark': '#3a362a' },
        tableCab: { DEFAULT: '#f5f5f5', bg: '#f5f5f5', dark: '#2a271c',  },
      },
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', '-apple-system', 'Segoe UI', 'Roboto', 'sans-serif'],
        display: ['"Space Grotesk"', 'Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
      },
      animation: {
        'fade-in-up':    'fadeInUp 0.6s ease-out forwards',
        'fade-in-up-d1': 'fadeInUp 0.6s ease-out 0.1s forwards',
        'fade-in-up-d2': 'fadeInUp 0.6s ease-out 0.2s forwards',
        'fade-in-up-d3': 'fadeInUp 0.6s ease-out 0.35s forwards',
        'shake':         'shake 0.5s ease-in-out',
        'blob-drift-a':  'blobDriftA 14s ease-in-out infinite alternate',
        'blob-drift-b':  'blobDriftB 18s ease-in-out infinite alternate',
        'shimmer':       'shimmer 3s linear infinite',
        // Playground streaming animations
        'slide-in-left':  'slideInLeft 0.3s ease-out forwards',
        'slide-in-right': 'slideInRight 0.3s ease-out forwards',
        'fade-in':        'fadeIn 0.2s ease-out forwards',
        'typing-dots':    'typingDots 1.4s ease-in-out infinite',
        'pulse-glow':     'pulseGlow 2s ease-in-out infinite',
        'blink-cursor':   'blinkCursor 1s step-end infinite',
        'tool-spin':      'toolSpin 1s linear infinite',
      },
      keyframes: {
        fadeInUp: {
          '0%':   { opacity: '0', transform: 'translateY(22px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        shake: {
          '0%, 100%':              { transform: 'translateX(0)' },
          '10%, 30%, 50%, 70%, 90%': { transform: 'translateX(-6px)' },
          '20%, 40%, 60%, 80%':    { transform: 'translateX(6px)' },
        },
        blobDriftA: {
          '0%':   { transform: 'translate(0px, 0px) scale(1)' },
          '50%':  { transform: 'translate(30px, -20px) scale(1.08)' },
          '100%': { transform: 'translate(-20px, 15px) scale(0.95)' },
        },
        blobDriftB: {
          '0%':   { transform: 'translate(0px, 0px) scale(1)' },
          '50%':  { transform: 'translate(-25px, 20px) scale(1.05)' },
          '100%': { transform: 'translate(20px, -15px) scale(0.97)' },
        },
        shimmer: {
          '0%':   { backgroundPosition: '-200% center' },
          '100%': { backgroundPosition: '200% center' },
        },
        // Playground streaming keyframes
        slideInLeft: {
          '0%':   { opacity: '0', transform: 'translateX(-12px)' },
          '100%': { opacity: '1', transform: 'translateX(0)' },
        },
        slideInRight: {
          '0%':   { opacity: '0', transform: 'translateX(12px)' },
          '100%': { opacity: '1', transform: 'translateX(0)' },
        },
        fadeIn: {
          '0%':   { opacity: '0' },
          '100%': { opacity: '1' },
        },
        typingDots: {
          '0%, 80%, 100%': { opacity: '0.3', transform: 'scale(0.8)' },
          '40%':           { opacity: '1',   transform: 'scale(1)' },
        },
        pulseGlow: {
          '0%, 100%': { opacity: '0.6', boxShadow: '0 0 4px rgba(99,102,241,0.3)' },
          '50%':      { opacity: '1',   boxShadow: '0 0 12px rgba(99,102,241,0.5)' },
        },
        blinkCursor: {
          '0%, 100%': { opacity: '1' },
          '50%':      { opacity: '0' },
        },
        toolSpin: {
          '0%':   { transform: 'rotate(0deg)' },
          '100%': { transform: 'rotate(360deg)' },
        },
      },
    },
  },
  plugins: [],
}
