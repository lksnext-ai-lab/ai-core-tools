# Mattin AI frontend

React 18 + TypeScript + Vite single-page app for Mattin AI. It is built into the `mattinai-frontend` Docker image (Nginx); it is not published as an npm package.

## Development

```bash
npm install
npm run dev      # Vite dev server on http://localhost:5173
npm run build    # Type-check + production build (dist/)
npm run lint
npm test
```

Configuration comes from `VITE_*` variables (see the root `CLAUDE.md`) or the runtime `window.__RUNTIME_CONFIG__` injected at container start. Architecture notes: [docs/architecture/frontend.md](../docs/architecture/frontend.md).

## License

This project is licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
