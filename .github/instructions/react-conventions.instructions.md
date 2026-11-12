---
description: Project-specific conventions for the Mattin AI React frontend — Vite library bundle, ExtensibleBaseApp, centralized api.ts, per-client extension via clientConfig.ts, and constants sync with the backend.
applyTo: "frontend/**"
---

# Mattin AI Frontend Conventions

These rules auto-apply whenever you edit any file under `frontend/`. Agents like `@react-expert` provide generic React 19 / TypeScript / Tailwind expertise; this file pins down the **Mattin-specific** paths, patterns and library/client extension model.

## Distribution Model: Library + Per-Client Apps

The frontend is built and **published as a reusable npm library** (`@lksnext/ai-core-tools-base`). Client deployments live in `clients/<name>/` and consume that library.

- **Base library** = `frontend/` — every page, component, context, theme, hook.
- **Client project** = `clients/<name>/` — imports the library and customizes ONLY via `src/config/clientConfig.ts` (theme, branding, auth config, API URL, feature flags, custom routes).
- **Never modify the base library to support a client-specific need** — extend via `clientConfig.ts` instead. If `clientConfig.ts` cannot express what the client needs, add the extension hook to the library API surface, not a hardcoded branch.

When working on a client project: read `clients/<name>/src/config/clientConfig.ts` first to understand what is overridden.

## Entry Point: `ExtensibleBaseApp`

`frontend/src/core/ExtensibleBaseApp.tsx` is the library's root component. Every client imports and renders it with their `clientConfig`. New top-level structural changes go through this component.

## File Structure (real paths)

```
frontend/src/
├── core/                # ExtensibleBaseApp (library entry) and config primitives
├── components/
│   ├── ui/              # Generic, reusable UI elements
│   ├── forms/           # Form components
│   └── playground/      # Agent playground UI
├── pages/               # Page-level components (one folder per route family)
├── services/            # api.ts — centralized HTTP client (see below)
├── contexts/            # React contexts: user, theme, settings
├── constants/           # Project-wide constants — KEEP IN SYNC WITH BACKEND DEFAULTS
├── auth/                # OIDC client + FAKE/LOCAL flows (matches backend AICT_LOGIN)
└── themes/              # Theme tokens (clients can override per-deployment)
```

## Networking: Always go through `services/api.ts`

ALL HTTP traffic to the backend MUST go through `frontend/src/services/api.ts`. This is the only place that knows about auth headers, base URLs, error normalization and OIDC token refresh.

- ❌ Do NOT call `fetch()` directly from a component, hook, page, or context.
- ❌ Do NOT call `axios` or any other HTTP client directly.
- ✅ Add a typed method to `api.ts` and call it from your component/hook.

Pattern:

```typescript
// services/api.ts
export const api = {
  agents: {
    list: () => httpGet<AgentSummary[]>('/internal/agents'),
    detail: (id: string) => httpGet<AgentDetail>(`/internal/agents/${id}`),
    create: (input: AgentCreate) => httpPost<AgentDetail>('/internal/agents', input),
  },
  // ...
};

// hook / component
const agents = await api.agents.list();
```

## Constants Synced with Backend

`frontend/src/constants/agentConstants.ts` holds values that **must match** backend defaults. If you change one side, change the other in the same commit.

| Constant | Frontend file | Backend equivalent |
|----------|---------------|--------------------|
| `DEFAULT_MEMORY_SUMMARIZE_THRESHOLD` (20) | `agentConstants.ts` | `Agent.memory_summarize_threshold` default in `backend/models/agent.py` |
| Memory max messages / tokens defaults | `agentConstants.ts` | `Agent.memory_max_messages`, `Agent.memory_max_tokens` defaults |

Add a row to this table whenever you introduce a new synced default.

`frontend/src/constants/messages.ts` holds user-facing strings. When translations matter, prefer i18n keys over hardcoded strings.

## State Management Decision Tree

| Scenario | Use |
|----------|-----|
| Local UI state | `useState` |
| State shared across siblings (1–3 components) | Lift to common parent |
| State shared across many components, simple shape | React Context in `contexts/` (e.g. `useUser`, `useTheme`) |
| Complex state with derived values, mutations from many places | Zustand store (collocate near feature) |

Do not introduce Redux/Jotai/Recoil for new features — the project standardizes on Context + Zustand.

## Styling, Dark Mode, Accessibility

- **Tailwind CSS** is the styling system. Use utility classes; do not introduce CSS Modules or styled-components without a strong reason.
- **Dark mode is required**: every screen must work in both light and dark using Tailwind's `dark:` variants.
- **Accessibility (WCAG 2.1)**: semantic HTML, keyboard-navigable controls, visible focus rings, `aria-label` for icon-only buttons, no color-only signaling.
- **Icons**: use the project's chosen icon library — do NOT introduce new icon libraries. Import individual icons, not the whole library.

## Frontend Design System

The Mattin AI frontend redesign is complete. The current UI is
the visual reference for all future frontend development.

When creating or modifying React components, pages, forms,
or other visual elements, read and follow:

`.github/instructions/frontend-design.instructions.md`

These design rules apply to all frontend development tasks,
not only explicit redesign requests.

Before implementing UI changes:
- Check `frontend/src/components/ui` for reusable components.
- Reuse existing components and their props or variants whenever possible.
- Follow the existing design tokens and CSS variables.
- Preserve visual consistency across new and existing features.
- Do not redesign unrelated components.
- Follow the project's Storybook conventions for reusable UI components.


## Auth Flows (mirror the backend)

`frontend/src/auth/` implements three modes that line up with backend `AICT_LOGIN`:

| Backend mode | Frontend behavior |
|--------------|------------------|
| `FAKE` | Simple email-only login form, calls `POST /internal/auth/dev-login` |
| `LOCAL` | Email + password form, calls the SaaS login endpoint |
| `OIDC` | Redirects to Azure Entra ID, handles callback and token refresh |

Route protection uses `ProtectedRoute` / `AdminRoute` components — wrap routes that require auth/admin instead of doing per-page checks.

## Vite Build & Commands

```bash
cd frontend
npm install
npm run dev                # Dev server on port 5173
npm run build:lib          # Build the publishable library bundle
npm run build:lib:watch    # Watch mode for library development
npm run lint               # ESLint
```

- **HMR**: keep top-level files free of side effects so HMR works
- **`import.meta.env.VITE_*`** for build-time env vars; never expose secrets
- **Bundle analysis**: visualize via `rollup-plugin-visualizer`; lazy-load heavy components with `React.lazy()` + `Suspense`
- **Static assets**: `public/` for direct serving, `src/assets/` to go through the bundler

## TypeScript

- `strict: true` is enabled — do not weaken it
- Never use `any`. Use `unknown` and narrow with a type guard
- Props interfaces: `readonly` on every field; export the interface separately from the component
- Discriminated unions instead of multiple optional fields when possible

## Anti-Patterns (project-specific)

- ❌ Direct `fetch()` or `axios` calls from components — route through `services/api.ts`
- ❌ Modifying the base library to support a single client — extend via `clientConfig.ts`
- ❌ Hardcoded API URLs — they come from `clientConfig.ts`
- ❌ Hardcoded user-facing strings when translations matter — use i18n keys
- ❌ New icon library introduced ad-hoc — use the project's existing one
- ❌ Forgetting the dark-mode variant on a new screen
- ❌ Adding a `useEffect` to derive state from props — compute inline or `useMemo`
- ❌ Drifting `agentConstants.ts` from backend defaults


## Internationalization (i18n)

All user-facing text in React components must use the
existing internationalization system.

This rule applies to both new components and modifications
to existing components.

- Never hardcode user-facing text in JSX or TypeScript.
- Use the project's existing i18n library and conventions.
- Before adding translations, inspect how i18n is implemented
  in similar components.
- Reuse existing translation keys whenever appropriate.
- Do not create duplicate keys for equivalent texts.
- When new keys are necessary, follow the existing naming
  conventions and namespaces.
- Add new translation keys to all supported locale files.
- Keep translation keys consistent across all languages.
- Translate labels, placeholders, buttons, validation messages,
  tooltips, modal titles, and accessibility text.
- Do not replace existing translation keys unnecessarily.
- Do not introduce a new internationalization library.
- Do not modify unrelated translations.

Before completing a UI task, verify that all newly introduced
user-facing text is internationalized and that the required
translation keys exist in all supported locales.
