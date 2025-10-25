# Client Frontend Project

This is a client-specific frontend project that extends the AI Core Tools base application.

## Project Structure

```
src/
├── components/          # Reusable UI components
│   └── ui/             # UI components (buttons, cards, etc.)
├── pages/              # Page components (routes)
├── config/             # Client configuration
├── themes/             # Custom theme overrides
├── App.tsx             # Main app with routing
└── main.tsx            # Entry point
```

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

### Overriding the Home Page
1. Create a custom home page component in `src/pages/`
2. Import it in `src/config/clientConfig.ts`
3. Add it to the `homePage` property in `clientConfig`

### Adding New Pages
1. Create a new page component in `src/pages/`
2. Add the route to `src/App.tsx` in the `extraRoutes` array
3. Add navigation item to `src/config/clientConfig.ts` in the `navigation.custom` array

### Adding New Components
1. Create reusable components in `src/components/`
2. Use the `useTheme()` hook to integrate with the theme system
3. Import and use in your pages

### Theme Integration
- Use `useTheme()` hook to access theme colors and settings
- Components automatically adapt to client's theme configuration
- Override theme in `src/themes/customTheme.ts`

## Backend

This frontend connects to the AI Core Tools backend API. Make sure the backend is running and accessible at the configured API URL.
