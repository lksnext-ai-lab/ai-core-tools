# Client Frontend Project

This is a client-specific frontend project that extends the AI Core Tools base application.

## Getting Started

1. Install dependencies:
   ```bash
   npm install
   ```

2. Configure your client settings:
   - Edit `src/config/clientConfig.ts` for client configuration
   - Edit `src/themes/customTheme.ts` for custom theming
   - Add your logo to `public/` directory

3. Start development server:
   ```bash
   npm run dev
   ```

## Customization

- **Theme**: Modify `src/themes/customTheme.ts` to customize colors, branding, etc.
- **Pages**: Add custom pages in `src/components/` and reference them in `src/App.tsx`
- **Configuration**: Update `src/config/clientConfig.ts` for client-specific settings

## Backend

This frontend connects to the AI Core Tools backend API. Make sure the backend is running and accessible at the configured API URL.
