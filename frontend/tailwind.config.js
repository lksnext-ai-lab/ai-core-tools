/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
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
