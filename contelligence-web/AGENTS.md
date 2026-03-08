# AGENTS.md — contelligence-web

React/TypeScript single-page application for the Contelligence platform. Provides the chat interface, session management, scheduling dashboard, agent/skill editors, and analytics.

## Tech stack

- React 18, TypeScript 5, Vite 7 (SWC plugin for fast builds)
- Tailwind CSS 3 with class-based dark mode
- Shadcn/ui (Radix UI primitives) — component library in `src/components/ui/`
- React Router 6 — client-side routing
- React Query (`@tanstack/react-query`) — server state management and caching
- react-hook-form + zod — form handling and validation
- Recharts — data visualization
- react-markdown + remark-gfm — markdown rendering
- Lucide React — icon library
- sonner — toast notifications

## Project structure

```
src/
├── components/          — Reusable components
│   ├── ui/              — Shadcn/ui primitives (Button, Dialog, Table, etc.)
│   ├── chat/            — Chat UI (message list, input, streaming display)
│   ├── outputs/         — Output artifact browser and preview
│   ├── schedules/       — Schedule management components
│   ├── settings/        — Settings forms
│   ├── AppLayout.tsx    — Main layout (sidebar, header, content area)
│   └── AppSidebar.tsx   — Navigation sidebar
├── pages/               — Route-level page components (lazy-loaded)
│   ├── Index.tsx         — Dashboard
│   ├── Chat.tsx          — Chat interface (SSE streaming)
│   ├── Sessions.tsx      — Session list
│   ├── Schedules.tsx     — Schedule dashboard
│   ├── Agents.tsx        — Agent library
│   ├── Skills.tsx        — Skill library
│   ├── Metrics.tsx       — Analytics
│   └── Settings.tsx      — Configuration
├── hooks/               — Custom React hooks
│   ├── useAgentStream.ts — SSE streaming and JSON event parsing
│   └── use-toast.tsx     — Toast notification hook
├── types/               — TypeScript type definitions
│   ├── index.ts          — SessionRecord, ToolCallRecord, OutputArtifact, etc.
│   └── agent-events.ts   — Agent event stream types
├── lib/                 — Utilities
│   ├── api.ts            — API client (fetch wrappers for /api/v1/)
│   ├── format.ts         — Date and number formatting
│   ├── turn-processing.ts — Conversation turn utilities
│   └── utils.ts          — cn() class merge helper, general utilities
├── App.tsx              — Root component (BrowserRouter, QueryClientProvider, routes)
├── main.tsx             — Entry point (ReactDOM.createRoot)
└── index.css            — Global styles (CSS variables, Tailwind directives)
```

## Key patterns

### Routing with lazy loading

```tsx
const ChatPage = lazy(() => import("@/pages/Chat"));
// Wrapped in <Suspense fallback={<PageLoader />}> in App.tsx
```

### Server state with React Query

```tsx
const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 5000, retry: 2, refetchOnWindowFocus: true },
  },
});
// All API data flows through useQuery/useMutation hooks
```

### API calls via lib/api.ts

```tsx
// Always use the typed API client — never fetch() directly in components
import { api } from "@/lib/api";
const sessions = await api.getSessions({ limit: 50 });
```

### Form validation with zod + react-hook-form

```tsx
const schema = z.object({ name: z.string().min(1), cron: z.string() });
const form = useForm({ resolver: zodResolver(schema) });
```

### Styling with Tailwind + Shadcn/ui

```tsx
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent } from "@/components/ui/dialog";
// Use Tailwind utilities — no inline styles, no CSS modules
```

### SSE streaming

```tsx
const { events, isStreaming } = useAgentStream(sessionId);
// Real-time agent events via Server-Sent Events
```

## Good examples to follow

- Pages: `src/pages/Chat.tsx` — SSE streaming, React Query, clean state management
- Components: `src/components/AppLayout.tsx` — layout composition with sidebar
- Hooks: `src/hooks/useAgentStream.ts` — SSE subscription pattern
- API client: `src/lib/api.ts` — typed fetch wrapper
- Types: `src/types/index.ts` — shared TypeScript interfaces

## Patterns to avoid

- Direct `fetch()` calls in components — use `lib/api.ts`
- Inline styles — use Tailwind utilities
- Class components — use functional components with hooks
- Local state for server data — use React Query
- Custom CSS files per component — use Tailwind + CSS variables in `index.css`

## Build and lint commands

```bash
# Development server with HMR
npm run dev

# Production build
npm run build

# Lint (ESLint with TypeScript rules)
npm run lint

# Type check
npx tsc --noEmit

# Run tests
npm test

# Preview production build
npm run preview
```

## Design system

- Components: Shadcn/ui wrappers live in `src/components/ui/` — use these, don't create parallel components
- Colors: CSS variables defined in `src/index.css` (supports dark mode)
- Fonts: Exo 2 (sans), Orbitron (display headings), JetBrains Mono (code)
- Icons: Lucide React — `import { IconName } from "lucide-react"`
- Path alias: `@/` maps to `src/` — always use `@/components/...`, `@/lib/...`, `@/pages/...`

## TypeScript configuration

- Strict mode is **relaxed** (`noImplicitAny: false`, `strictNullChecks: false`)
- Path alias: `@/*` → `./src/*`
- `allowJs: true`, `skipLibCheck: true`
- Target: ES2020, module: ESNext
