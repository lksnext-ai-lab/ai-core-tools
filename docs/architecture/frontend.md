# Frontend Architecture

> Part of [Mattin AI Documentation](../README.md)

## Overview

The frontend is a **React 18 + TypeScript** application built using **Vite** as the build tool. It follows a **library + client** architecture:

- **Base Library** (`@lksnext/ai-core-tools-base`): Core reusable components, hooks, contexts, and services
- **Client Projects** (`clients/*`): Custom branded applications that consume the base library with client-specific themes and configurations

This architecture enables **single codebase, multiple brands** — one set of core components powers multiple client applications.

## Architecture Pattern

```
┌─────────────────────────────────────────────┐
│          Client Project (e.g., LKS)         │
│  ┌──────────────┐  ┌─────────────────┐     │
│  │ clientConfig │  │  Custom Theme   │     │
│  │   (branding) │  │  (colors, logo) │     │
│  └──────────────┘  └─────────────────┘     │
└─────────────────────────────────────────────┘
                    │
                    │ imports
                    ▼
┌─────────────────────────────────────────────┐
│   @lksnext/ai-core-tools-base (Library)     │
│  ┌──────────────┐  ┌─────────────────┐     │
│  │    Core      │  │   Components    │     │
│  │ (BaseApp)    │  │  (Playground,   │     │
│  │              │  │   Settings,     │     │
│  └──────────────┘  │   Forms, UI)    │     │
│                    └─────────────────┘     │
│  ┌──────────────┐  ┌─────────────────┐     │
│  │  Contexts    │  │    Services     │     │
│  │ (User, Theme)│  │    (api.ts)     │     │
│  └──────────────┘  └─────────────────┘     │
└─────────────────────────────────────────────┘
                    │
                    │ HTTP requests
                    ▼
            Backend API (/internal/*)
```

## Base Library Structure

### Core (`src/core/`)

**Entry point**: `ExtensibleBaseApp` component

The base app provides:
- **Routing** (React Router)
- **Authentication** (OIDC or FAKE mode)
- **Theme management** (light/dark mode)
- **Global contexts** (user, theme, apps)
- **Layout** (header, sidebar, footer)

**Usage in client projects**:
```tsx
import { ExtensibleBaseApp } from '@lksnext/ai-core-tools-base';
import clientConfig from './config/clientConfig';

function App() {
  return <ExtensibleBaseApp config={clientConfig} />;
}
```

### Pages (`src/pages/`)

**34+ page components** organized by category:

#### Main Pages (24 pages)

| Page | Route | Purpose |
|------|-------|---------|
| **Home** | `/` | Landing page with app selection |
| **Playground** | `/playground` | Agent interaction interface |
| **Agents** | `/agents` | Agent list and management |
| **Silos** | `/silos` | Vector store management |
| **Repositories** | `/repositories` | File repository management |
| **Domains** | `/domains` | Web domain management |
| **Conversations** | `/conversations` | Conversation history |
| **Login/Callback** | `/login`, `/callback` | OIDC authentication flow |

#### Settings Pages (8 pages)

| Page | Route | Purpose |
|------|-------|---------|
| **Settings Home** | `/settings` | Settings overview |
| **Agents Settings** | `/settings/agents` | Agent configuration |
| **Silos Settings** | `/settings/silos` | Vector store configuration |
| **Repositories Settings** | `/settings/repositories` | Repository configuration |
| **Domains Settings** | `/settings/domains` | Domain configuration |
| **AI Services Settings** | `/settings/ai-services` | LLM provider configuration |
| **Embedding Services Settings** | `/settings/embedding-services` | Embedding model configuration |
| **Collaboration Settings** | `/settings/collaboration` | App collaboration management |

#### Admin Pages (2 pages)

| Page | Route | Purpose |
|------|-------|---------|
| **Admin Dashboard** | `/admin` | Admin overview |
| **User Management** | `/admin/users` | User administration |

### Components (`src/components/`)

Reusable UI components organized by category:

#### UI Components (`src/components/ui/`)

Generic, reusable UI elements:
- **Button**: Primary, secondary, danger variants
- **Input**: Text, number, textarea with validation
- **Select**: Dropdown with search
- **Modal**: Overlays and dialogs
- **Card**: Content containers
- **Tabs**: Tabbed interfaces
- **Table**: Data tables with sorting/filtering
- **Spinner**: Loading indicators
- **Toast**: Notifications

#### Forms (`src/components/forms/`)

Specialized form components:
- **AgentForm**: Agent configuration form
- **SiloForm**: Vector store configuration form
- **RepositoryForm**: Repository creation form
- **DomainForm**: Domain management form
- **AIServiceForm**: LLM provider configuration
- **EmbeddingServiceForm**: Embedding model configuration

#### Playground (`src/components/playground/`)

Agent interaction interface components:
- **ChatInterface**: Message list and input
- **AgentSelector**: Agent selection dropdown
- **ConversationHistory**: Conversation list
- **MessageBubble**: Individual message rendering
- **StreamingIndicator**: Typing indicator for streaming responses

#### Layout (`src/components/layout/`)

App structure components:
- **Header**: Top navigation bar
- **Sidebar**: Side navigation menu
- **Footer**: Footer with links and version info
- **PageContainer**: Page wrapper with consistent spacing

#### Settings (`src/components/settings/`)

Settings page components:
- **AgentsSettings**: Agent management UI
- **SilosSettings**: Vector store management
- **RepositoriesSettings**: Repository management
- **DomainsSettings**: Domain management
- **AIServicesSettings**: LLM provider management
- **CollaborationSettings**: App collaboration UI

### Contexts & State Management

React Context API for global state:

| Context | Purpose |
|---------|---------|
| **UserContext** | Current user, authentication state |
| **ThemeContext** | Theme (light/dark), customization |
| **SettingsCacheContext** | Cache for settings data (agents, silos, etc.) |

**Usage**:
```tsx
import { useUser } from '@lksnext/ai-core-tools-base';

function MyComponent() {
  const { user, isAuthenticated } = useUser();
  return <div>{user?.name}</div>;
}
```

### Hooks (`src/hooks/`)

Custom React hooks for common patterns:

| Hook | Purpose |
|------|---------|
| **useAppRole** | Get user's role in current app |
| **useFormState** | Form state management with validation |
| **useServicesManager** | Manage AI/embedding services |
| **useSettingsData** | Load and cache settings data |
| **useSettingsModal** | Modal state for settings forms |
| **useApi** | Wrapper for API calls with loading/error states |
| **useAuth** | Authentication utilities |
| **useTheme** | Theme access and modification |
| **useLocalStorage** | Persistent local storage |
| **useDebounce** | Debounced values for search/filters |

### Services (`src/services/`)

**Centralized API client**: `api.ts`

All backend communication goes through the `api` service:

```typescript
import api from '@lksnext/ai-core-tools-base/services/api';

// Agents
const agents = await api.agents.list(appId);
const agent = await api.agents.get(appId, agentId);
await api.agents.create(appId, agentData);

// Silos
const silos = await api.silos.list(appId);

// Conversations
const messages = await api.conversations.getMessages(conversationId);
```

Additional service modules:
- **auth.ts**: Authentication utilities
- **admin.ts**: Admin operations

**Anti-pattern**: Never use `fetch()` directly in components. Always use the `api` service.

### Theming

**ThemeProvider** wraps the entire app with theme context:

```tsx
<ThemeProvider theme={customTheme}>
  <App />
</ThemeProvider>
```

**Base theme** (`baseTheme`): Default Mattin AI theme
**Custom themes**: Override base theme via `clientConfig`

```typescript
const customTheme = {
  ...baseTheme,
  colors: {
    ...baseTheme.colors,
    primary: '#1E3A8A',    // Custom brand color
    secondary: '#0EA5E9',
  },
};
```

**Tailwind CSS** utility-first approach with theme integration:

```tsx
<button className="bg-primary hover:bg-primary-dark text-white font-bold py-2 px-4 rounded">
  Click Me
</button>
```

### Authentication

**AuthContext** provides authentication state and utilities:

```tsx
import { useAuth } from '@lksnext/ai-core-tools-base';

function MyComponent() {
  const { user, login, logout, isAuthenticated } = useAuth();
  // ...
}
```

**OIDC integration** (via `lks-idprovider-fastapi`):
- **OIDCProvider**: Wraps app with OIDC context
- **AuthConfig**: Configuration (client ID, authority, scopes)

**Protected routes**:
- `ProtectedRoute`: Requires authentication
- `AdminRoute`: Requires admin/omniadmin role

**OIDC flow**:
1. User clicks login
2. Redirect to OIDC provider (EntraID/Azure AD)
3. Provider redirects to `/callback` with auth code
4. Backend exchanges code for tokens
5. Session cookie set, user redirected to app

**FAKE mode** (development): Skip OIDC, use mock user.

### Navigation

**defaultNavigation**: Default navigation structure (sidebar menu items)

```typescript
const defaultNavigation = [
  { name: 'Home', path: '/', icon: HomeIcon },
  { name: 'Playground', path: '/playground', icon: ChatIcon },
  { name: 'Settings', path: '/settings', icon: SettingsIcon },
  // ...
];
```

**NavigationMerger**: Merges default navigation with client-specific or plugin navigation items

**Plugin System** (extensibility point):
Client projects can extend the base app with:
- **Custom pages**: Add new routes
- **Custom navigation items**: Add to sidebar
- **Custom components**: Override base components
- **Custom themes**: Full theming control

## Client Project Structure

Example: `clients/lks/`

```
clients/lks/
├── src/
│   ├── config/
│   │   └── clientConfig.ts     # Client-specific config
│   ├── themes/
│   │   └── lksTheme.ts         # Custom LKS theme
│   ├── assets/
│   │   └── logo.svg            # LKS logo
│   ├── App.tsx                 # App entry (uses ExtensibleBaseApp)
│   └── main.tsx                # Vite entry point
├── public/
│   └── favicon.ico             # LKS favicon
├── package.json                # Dependencies (includes base library)
└── vite.config.ts              # Vite configuration
```

### Client Configuration

`clientConfig.ts` customizes the base app:

```typescript
import { ClientConfig } from '@lksnext/ai-core-tools-base';
import lksTheme from '../themes/lksTheme';
import logo from '../assets/logo.svg';

const config: ClientConfig = {
  client_id: 'lks',
  client_name: 'LKS Next',
  theme: lksTheme,
  logo: logo,
  // Custom pages, routes, components (optional)
};

export default config;
```

## Build & Development

### Development

```bash
cd frontend
npm install
npm run dev       # Start Vite dev server on http://localhost:5173
```

### Production Build

```bash
npm run build     # Build for production (output to dist/)
npm run preview   # Preview production build
```

### Library Build

```bash
npm run build:lib # Build base library for npm publishing
```

## Testing

- **React Testing Library**: Component tests
- **Jest**: Unit tests
- **Playwright** (optional): End-to-end tests

## Key Design Patterns

### Component Composition

Break complex UI into small, reusable components:

```tsx
<Playground>
  <AgentSelector />
  <ChatInterface>
    <ConversationHistory />
    <MessageList />
    <MessageInput />
  </ChatInterface>
</Playground>
```

### Props Drilling Avoidance

Use Context API for deeply nested data:

```tsx
// Instead of props drilling:
<Parent user={user}>
  <Child user={user}>
    <GrandChild user={user} />  ❌
  </Child>
</Parent>

// Use context:
<UserProvider>
  <Parent>
    <Child>
      <GrandChild />            ✅ (uses useUser())
    </Child>
  </Parent>
</UserProvider>
```

### Controlled Components

Forms use controlled inputs (state-managed values):

```tsx
const [name, setName] = useState('');
<input value={name} onChange={(e) => setName(e.target.value)} />
```

## See Also

- [Architecture Overview](overview.md)
- [Backend Architecture](backend.md)
- [Client Project Setup](../guides/client-setup.md)
- [Authentication Guide](../guides/authentication.md)
- [Plugin Development](../guides/plugin-development.md)
