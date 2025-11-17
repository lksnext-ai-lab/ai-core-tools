/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        primary: 'var(--color-primary, #3b82f6)',
        secondary: 'var(--color-secondary, #8b5cf6)',
        accent: 'var(--color-accent, #06b6d4)',
        background: 'var(--color-background, #f9fafb)',
        surface: 'var(--color-surface, #ffffff)',
        text: 'var(--color-text, #111827)',
      }
    },
  },
  plugins: [],
}
