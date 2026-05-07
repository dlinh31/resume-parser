# Plan: Repo Restructure + Frontend Scaffold

## Phase 0: Discovery Findings (Complete)

### Python audit key facts
- `alembic.ini` uses `script_location = alembic` (relative) — `alembic` must be invoked from `server/`
- `alembic/env.py` imports `from resume_parser.db.models import Base` — works via `prepend_sys_path = .` in alembic.ini when run from `server/`
- `.env` keys: `ANTHROPIC_API_KEY`, `DATABASE_URL`, `OPENAI_API_KEY` (plus `DOCAI_*` vars referenced in extract.py but not currently in `.env`) — all go to `server/.env`
- `PARSED_DIR = Path("data/parsed")` in `extract.py` is cwd-relative — correct if server is run from `server/`; only hit by CLI batch mode (API path uses tempdir)
- `app.py` has **no CORS middleware** — must add before client can call API

### Frontend library key facts
- **TanStack Query v5:** `gcTime` (not `cacheTime`), `isPending` (not `isLoading`), `status === 'pending'` (not `'loading'`), no `onSuccess`/`onError` callbacks on `useQuery`
- **Zustand v5:** `create<State>()((set) => ...)` double-call syntax required with TypeScript; `useShallow` from `zustand/react/shallow`
- **React Hook Form + Zod file input:** use `z.custom<FileList>()` not `z.instanceof(FileList)`; file is at `data.file[0]`
- **@hey-api/openapi-ts:** requires two packages — `@hey-api/openapi-ts` (dev) + `@hey-api/client-fetch` (runtime); fast-moving, verify version after install

---

## Phase 1: Python Repo Restructure → `server/`

**Goal:** All Python, Alembic, and data files live under `server/`. CLI commands work unchanged from within `server/`.

### Anti-patterns
- Do NOT edit `alembic.ini` values — the relative paths are correct as-is
- Do NOT edit any Python imports — package layout is preserved
- Do NOT use `git add -A` — stage files explicitly

### Tasks

1. Create `server/` directory
2. `git mv` all tracked Python files into `server/`:
   ```bash
   git mv src server/src
   git mv alembic server/alembic
   git mv alembic.ini server/alembic.ini
   git mv pyproject.toml server/pyproject.toml
   git mv data server/data
   ```
3. Create `server/.env` — copy all keys from root `.env`:
   - `ANTHROPIC_API_KEY`
   - `DATABASE_URL`
   - `OPENAI_API_KEY`
   - Any `DOCAI_*` vars if present
4. Delete root `.env` (tracked deletion via git rm or just remove since it's gitignored)
5. Recreate the venv from `server/` (old `.venv` is gitignored, just delete and rebuild):
   ```bash
   rm -rf .venv
   cd server
   python -m venv .venv
   .venv/bin/pip install -e .
   ```
6. Update root `.gitignore`:
   - Replace bare `data/` with `server/data/`
   - Replace bare `.venv/` with `server/.venv/`
   - Add `client/node_modules/`
   - Add `client/dist/`
   - Add `client/.env`
7. Update `CLAUDE.md` — change all path references from repo root to `server/` prefix

### Verification
```bash
cd server
.venv/bin/serve                        # FastAPI starts on :8000
.venv/bin/alembic current             # shows current migration head
# optional: .venv/bin/ingest data/raw/resumes/
```

---

## Phase 2: Add CORS Middleware to FastAPI

**Goal:** FastAPI allows cross-origin requests from `http://localhost:5173` (Vite dev server).

### File: `server/src/resume_parser/api/app.py`

Add after the existing imports:
```python
from fastapi.middleware.cors import CORSMiddleware
```

Add after `app = FastAPI(lifespan=lifespan)`:
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### Verification
```bash
# With server running:
curl -s -I -H "Origin: http://localhost:5173" http://localhost:8000/openapi.json \
  | grep -i access-control
# Should print: access-control-allow-origin: http://localhost:5173
```

---

## Phase 3: Scaffold `client/`

**Goal:** Vite + React + TypeScript project at `client/` with all libraries installed and configured.

### 3a. Create Vite project

```bash
npm create vite@latest client -- --template react-ts
cd client
npm install
```

### 3b. Install all libraries

```bash
# Tailwind v4 (Vite plugin — no tailwind.config.js)
npm install tailwindcss @tailwindcss/vite

# shadcn/ui (Tailwind v4 supported in shadcn v2+)
npx shadcn@latest init

# TanStack Router + file-based routing plugin
npm install @tanstack/react-router @tanstack/router-devtools
npm install -D @tanstack/router-plugin

# TanStack Query v5
npm install @tanstack/react-query @tanstack/react-query-devtools

# Zustand v5
npm install zustand

# React Hook Form + Zod
npm install react-hook-form @hookform/resolvers zod

# hey-api openapi client generator
npm install -D @hey-api/openapi-ts
npm install @hey-api/client-fetch
```

### 3c. Configure `vite.config.ts`

Replace generated config with:
```ts
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { TanStackRouterVite } from '@tanstack/router-plugin/vite'
import path from 'path'

export default defineConfig({
  plugins: [
    TanStackRouterVite({ routesDirectory: './src/routes' }),
    react(),
    tailwindcss(),
  ],
  resolve: {
    alias: { '@': path.resolve(__dirname, './src') },
  },
})
```

Note: `TanStackRouterVite` must come before `react()`.

### 3d. Configure Tailwind in CSS

In `src/index.css` (created by shadcn init), ensure the first line is:
```css
@import "tailwindcss";
```
Remove any legacy `@tailwind base/components/utilities` directives.

### 3e. Configure openapi-ts

Create `client/openapi-ts.config.ts`:
```ts
import { defineConfig } from '@hey-api/openapi-ts'

export default defineConfig({
  client: '@hey-api/client-fetch',
  input: 'http://localhost:8000/openapi.json',
  output: {
    path: 'src/client',
    format: 'prettier',
  },
  plugins: ['@tanstack/react-query'],
})
```

Add to `package.json` scripts:
```json
"generate-client": "openapi-ts"
```

### 3f. Create `client/.env`

```
VITE_API_URL=http://localhost:8000
```

### Verification
```bash
cd client
npm run dev     # starts on http://localhost:5173, no errors
npx tsc --noEmit  # zero TypeScript errors
```

---

## Phase 4: Wire Providers, Routes, and Placeholder Pages

**Goal:** TanStack Router file-based routing active, QueryClientProvider wrapping app, Zustand store defined, three navigable placeholder pages.

### 4a. Update `src/main.tsx`

```tsx
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { RouterProvider, createRouter } from '@tanstack/react-router'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createClient } from '@hey-api/client-fetch'
import { routeTree } from './routeTree.gen'
import './index.css'

createClient({ baseUrl: import.meta.env.VITE_API_URL })

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 60 * 5,
      gcTime: 1000 * 60 * 10,
      retry: 1,
    },
  },
})

const router = createRouter({ routeTree })

declare module '@tanstack/react-router' {
  interface Register { router: typeof router }
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </StrictMode>,
)
```

### 4b. Create route files

**`src/routes/__root.tsx`** — root layout:
```tsx
import { createRootRoute, Outlet, Link } from '@tanstack/react-router'
import { ReactQueryDevtools } from '@tanstack/react-query-devtools'
import { TanStackRouterDevtools } from '@tanstack/router-devtools'

export const Route = createRootRoute({
  component: () => (
    <>
      <nav>
        <Link to="/">Upload</Link>
        <Link to="/resumes">Resumes</Link>
      </nav>
      <Outlet />
      <ReactQueryDevtools initialIsOpen={false} />
      <TanStackRouterDevtools />
    </>
  ),
})
```

**`src/routes/index.tsx`** — Upload page:
```tsx
import { createFileRoute } from '@tanstack/react-router'

export const Route = createFileRoute('/')({
  component: UploadPage,
})

function UploadPage() {
  return <div>Upload page — placeholder</div>
}
```

**`src/routes/resumes.tsx`** — Resume list:
```tsx
import { createFileRoute } from '@tanstack/react-router'

export const Route = createFileRoute('/resumes')({
  component: ResumesPage,
})

function ResumesPage() {
  return <div>Resume list — placeholder</div>
}
```

**`src/routes/resumes.$fileId.tsx`** — Resume detail:
```tsx
import { createFileRoute } from '@tanstack/react-router'

export const Route = createFileRoute('/resumes/$fileId')({
  component: ResumeDetailPage,
})

function ResumeDetailPage() {
  const { fileId } = Route.useParams()
  return <div>Resume detail — {fileId}</div>
}
```

### 4c. Create Zustand store

**`src/store/useAppStore.ts`**:
```ts
import { create } from 'zustand'
import { devtools } from 'zustand/middleware'

interface AppState {
  uploadStatus: 'idle' | 'uploading' | 'done' | 'error'
  activeJobId: string | null
  setUploadStatus: (status: AppState['uploadStatus']) => void
  setActiveJobId: (id: string | null) => void
}

export const useAppStore = create<AppState>()(
  devtools(
    (set) => ({
      uploadStatus: 'idle',
      activeJobId: null,
      setUploadStatus: (status) => set({ uploadStatus: status }),
      setActiveJobId: (id) => set({ activeJobId: id }),
    }),
    { name: 'AppStore' }
  )
)
```

### 4d. Generate typed API client (requires server running)

```bash
# In one terminal: cd server && .venv/bin/serve
# In another:
cd client && npm run generate-client
# Produces: src/client/types.gen.ts, services.gen.ts, index.ts, @tanstack/ hooks
```

### Verification
```bash
cd client
npm run dev                # all three routes navigate without errors
npx tsc --noEmit          # zero TypeScript errors
# Verify routeTree.gen.ts was auto-generated in src/
```

---

## Final State

```
resume-parser/
  server/
    src/resume_parser/    # Python package (moved)
    alembic/              # migrations (moved)
    alembic.ini           # (moved)
    pyproject.toml        # (moved)
    .venv/                # (recreated)
    data/                 # pipeline I/O (moved)
    .env                  # server secrets
  client/
    src/
      routes/             # __root.tsx, index.tsx, resumes.tsx, resumes.$fileId.tsx
      store/              # useAppStore.ts
      client/             # generated by openapi-ts
      main.tsx
      index.css
    openapi-ts.config.ts
    vite.config.ts
    package.json
    .env                  # VITE_API_URL
  .gitignore              # updated
  CLAUDE.md               # updated
  plans/
```
