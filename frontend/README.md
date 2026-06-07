# MediaTranX — Frontend

Vue 3 + TypeScript + Pinia + Vite frontend for MediaTranX. Part of the monorepo;
the Electron shell (`../electron`) wraps this together with the FastAPI backend
(`../backend`). See [`../docs/FRONTEND_DEVELOP_SPEC.md`](../docs/FRONTEND_DEVELOP_SPEC.md)
for UI/UX conventions and [`../docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md) for the big picture.

## Recommended IDE

[VSCode](https://code.visualstudio.com/) + [Vue (Official)](https://marketplace.visualstudio.com/items?itemName=Vue.volar) (disable Vetur).
`.vue` type-checking uses `vue-tsc` instead of `tsc`.

## Setup

```sh
npm install
```

## Scripts

```sh
npm run dev          # Vite dev server (default port 5173; Electron injects VITE_PORT=8000)
npm run build        # type-check + production build (run-p type-check build-only)
npm run type-check   # vue-tsc --build — must stay at 0 errors
npm run lint         # eslint . --fix
npm run test         # vitest run
```

> For a packaged build, the frontend is compiled via the repo-root build script —
> `uv run --project backend python scripts/build.py --step vite` (uses `vite build` with the
> Electron output paths), not a bare `npm run build`. See [`../docs/BUILD_STRATEGY.md`](../docs/BUILD_STRATEGY.md).
