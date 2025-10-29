# @lksnext/ai-core-tools-base

Base React components and utilities for AI Core Tools - an extensible AI toolbox platform.

## Installation

```bash
npm install @lksnext/ai-core-tools-base
```

## Usage

```tsx
import { ExtensibleBaseApp, Header, Sidebar, Layout } from '@lksnext/ai-core-tools-base';
import '@lksnext/ai-core-tools-base/dist/style.css';

function App() {
  return (
    <ExtensibleBaseApp
      config={{
        // Your configuration
      }}
    />
  );
}
```

## Development

### Building the Library

```bash
npm run build:lib
```

This builds the library into the `dist/` directory with both ESM and CommonJS formats.

### Watch Mode

```bash
npm run build:lib:watch
```

### Local Testing

```bash
npm run pack:local
```

This creates a `.tgz` file that can be installed locally:
```bash
npm install ./lksnext-ai-core-tools-base-0.3.0.tgz
```

## Publishing

### Prerequisites

1. **Create an npm account** (if you don't have one):
   - Sign up at [npmjs.com](https://www.npmjs.com/signup)
   
2. **Login to npm** (first time only):
   ```bash
   npm login
   ```

### Publishing Process

1. **Update version** in `package.json` (following [semver](https://semver.org/))

2. **Test before publishing**:
   ```bash
   npm run publish:npm:dry-run
   ```

3. **Publish to npm**:
   ```bash
   npm run publish:npm
   ```
   
   Or use the provided script:
   ```bash
   ./deploy/scripts/publish-library.sh
   ```

### Publishing Options

- **npm Registry (Public)** - Recommended for OSS projects
  - Free for public packages
  - Most developers expect packages here
  - Easy to use: `npm run publish:npm`
  
- **GitHub Packages** - Alternative option
  - If you prefer GitHub ecosystem
  - Requires additional `.npmrc` configuration
  
- **Private Registry** - For internal use
  - Use your organization's private npm registry
  - Configure via `.npmrc`

## Package Information

- **Name**: `@lksnext/ai-core-tools-base`
- **License**: AGPL-3.0
- **Repository**: [GitHub](https://github.com/lksnext-ai-lab/ai-core-tools)
- **Package URL**: [npmjs.com/package/@lksnext/ai-core-tools-base](https://www.npmjs.com/package/@lksnext/ai-core-tools-base)

## License

This project is licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).

---

## Expanding the ESLint configuration

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
