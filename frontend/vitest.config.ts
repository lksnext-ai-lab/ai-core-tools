import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

/**
 * Render tests (Vitest + React Testing Library). Kept apart from `vite.config.ts` so the app and library
 * builds are untouched. The pure-logic harness (`tests/*.test.cjs`, `node --test`) is a separate runner.
 */
export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    include: ['tests/ui/**/*.test.{ts,tsx}'],
    setupFiles: ['tests/ui/setup.ts'],
    css: false,
    clearMocks: true,
    // Undo spies (e.g. a silenced console.error) after each test so they cannot hide warnings in later ones.
    restoreMocks: true,
    testTimeout: 15000,
  },
});
