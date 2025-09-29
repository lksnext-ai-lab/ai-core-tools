# React + TypeScript + Vite

This frontend now ships with a built-in OpenID Connect (OIDC) flow that enables Microsoft, Google and Keycloak single sign-on without relying on the backend. The application performs the PKCE flow entirely from the browser and stores tokens in memory only.

## Configuring identity providers

Configure providers through Vite environment variables (e.g. `.env.local`). Only the authority and client ID are required—everything else has sensible defaults.

```bash
# Microsoft
VITE_OIDC_MICROSOFT_AUTHORITY=https://login.microsoftonline.com/<tenant-id>/v2.0
VITE_OIDC_MICROSOFT_CLIENT_ID=<app-client-id>
VITE_OIDC_MICROSOFT_REDIRECT_URI=http://localhost:5173/auth/callback
VITE_OIDC_MICROSOFT_LOGOUT_REDIRECT_URI=http://localhost:5173/login

# Google
VITE_OIDC_GOOGLE_AUTHORITY=https://accounts.google.com
VITE_OIDC_GOOGLE_CLIENT_ID=<app-client-id>
VITE_OIDC_GOOGLE_REDIRECT_URI=http://localhost:5173/auth/callback
VITE_OIDC_GOOGLE_LOGOUT_REDIRECT_URI=http://localhost:5173/login

# Keycloak
VITE_OIDC_KEYCLOAK_AUTHORITY=https://keycloak.example.com/realms/<realm>
VITE_OIDC_KEYCLOAK_CLIENT_ID=<app-client-id>
VITE_OIDC_KEYCLOAK_REDIRECT_URI=http://localhost:5173/auth/callback
VITE_OIDC_KEYCLOAK_LOGOUT_REDIRECT_URI=http://localhost:5173/login
```

If more than one provider is configured, the login page renders a button for each. The redirect URI must match the `/auth/callback` route that processes OIDC responses.

---

This template provides a minimal setup to get React working in Vite with HMR and some ESLint rules.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Babel](https://babeljs.io/) for Fast Refresh
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/) for Fast Refresh

## Expanding the ESLint configuration

If you are developing a production application, we recommend updating the configuration to enable type-aware lint rules:

```js
export default tseslint.config([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      // Other configs...

      // Remove tseslint.configs.recommended and replace with this
      ...tseslint.configs.recommendedTypeChecked,
      // Alternatively, use this for stricter rules
      ...tseslint.configs.strictTypeChecked,
      // Optionally, add this for stylistic rules
      ...tseslint.configs.stylisticTypeChecked,

      // Other configs...
    ],
    languageOptions: {
      parserOptions: {
        project: ['./tsconfig.node.json', './tsconfig.app.json'],
        tsconfigRootDir: import.meta.dirname,
      },
      // other options...
    },
  },
])
```

You can also install [eslint-plugin-react-x](https://github.com/Rel1cx/eslint-react/tree/main/packages/plugins/eslint-plugin-react-x) and [eslint-plugin-react-dom](https://github.com/Rel1cx/eslint-react/tree/main/packages/plugins/eslint-plugin-react-dom) for React-specific lint rules:

```js
// eslint.config.js
import reactX from 'eslint-plugin-react-x'
import reactDom from 'eslint-plugin-react-dom'

export default tseslint.config([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      // Other configs...
      // Enable lint rules for React
      reactX.configs['recommended-typescript'],
      // Enable lint rules for React DOM
      reactDom.configs.recommended,
    ],
    languageOptions: {
      parserOptions: {
        project: ['./tsconfig.node.json', './tsconfig.app.json'],
        tsconfigRootDir: import.meta.dirname,
      },
      // other options...
    },
  },
])
```
