# NOVA dashboard

React + TypeScript + Vite dashboard for NOVA, the offline storage optimizer.
Talks to the FastAPI backend in `../backend` over its five live endpoints:
`/health`, `/api/guardrails/check`, `/api/apt-clutter/scan`, `/api/audit-log`,
and `/api/audit-log/verify`.

## Stack

- React 19 + TypeScript, built with Vite
- Tailwind CSS v4 for styling (light/dark theme, persisted toggle)
- React Router for the Dashboard / Storage cleanup / Guardrails / Audit log pages
- TanStack Query for data fetching, caching, and polling
- oxlint for linting

## Getting started

```sh
npm install
npm run dev
```

The dev server proxies `/api/*` and `/health` to the backend (see
`vite.config.ts`) so the browser never has to deal with cross-origin
requests. It targets `http://127.0.0.1:8756` by default, matching
`packaging/systemd/nova.service`. If you're running the backend locally with
a bare `uvicorn backend.app.main:app --reload` (which defaults to port
8000), point the proxy at it instead:

```sh
NOVA_BACKEND_URL=http://127.0.0.1:8000 npm run dev
```

## Scripts

- `npm run dev` — start the Vite dev server
- `npm run build` — type-check (`tsc -b`) and build for production
- `npm run typecheck` — type-check only
- `npm run lint` — run oxlint
- `npm run preview` — preview a production build locally

## Structure

```
src/
  components/
    layout/     shell, sidebar, topbar, theme toggle
    ui/         shared primitives (Card, Badge, Button, table states, ...)
    dashboard/  dashboard-only widgets
    clutter/    storage-cleanup page widgets
    guardrails/ guardrails page widgets
    audit/      audit-log page widgets
  hooks/        TanStack Query hooks wrapping lib/api.ts
  lib/          API client, formatting helpers, cn()
  pages/        one component per route
  types/        response types mirrored from backend/app/main.py
```

## Notes

- This dashboard isn't wired into the Debian/systemd packaging yet (see
  `../packaging/README.md`) — there's no build/serve story for it in
  production. It's dev-only for now, run via `npm run dev` or `npm run
  preview`.
- No values are hardcoded from `backend/config/settings.py` (scan roots,
  protected-paths config, audit log path) — those aren't exposed over the
  API, so the UI doesn't assume anything about them beyond what each
  endpoint returns.
