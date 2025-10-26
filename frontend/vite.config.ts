import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig(({ mode }) => {
  if (mode === 'library') {
    return {
      plugins: [react()],
      build: {
        lib: {
          entry: path.resolve(__dirname, 'src/index.ts'),
          name: 'AICoreToolsBase',
          formats: ['es', 'cjs'],
          fileName: (format) => `index.${format === 'es' ? 'js' : 'cjs'}`
        },
        rollupOptions: {
          external: [
            'react', 
            'react-dom', 
            'react-router-dom',
            'axios',
            'oidc-client-ts',
            'react-markdown'
          ],
          output: {
            globals: {
              react: 'React',
              'react-dom': 'ReactDOM',
              'react-router-dom': 'ReactRouterDOM',
              'axios': 'axios',
              'oidc-client-ts': 'oidc-client-ts',
              'react-markdown': 'ReactMarkdown'
            },
            assetFileNames: (assetInfo) => {
              if (assetInfo.name?.endsWith('.css')) {
                return 'style.css';
              }
              return assetInfo.name || 'asset';
            }
          }
        },
        cssCodeSplit: false,
        minify: 'terser',
        sourcemap: true,
        target: 'es2020'
      }
    };
  }

  // Default dev/build config
  return {
    plugins: [react()],
    server: {
      port: 5173
    }
  };
});
