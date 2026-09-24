# Bot dashboard

Admin UI for the bot: overview (block scanner, fetchers, dedup, curve, RUNE transfers, users),
scheduled jobs (list / create / edit / run now / apply), scheduler logs and feature flags.

- Frontend: Vue 3 + PrimeVue 4 (MIT, pinned `<5`: PrimeVue 5 needs a commercial license key) + Vite, plain JS.
- Backend: FastAPI app in `app/dashboard/`, entry point `app/dashboard_api.py`. It serves `/api/*` and the built SPA.
- Production: `docker compose up dashboard` builds both (see `web/Dockerfile-dashboard`); nginx proxies
  `/dashboard/` with basic auth. API docs: `/dashboard/api/docs`.

## Local development

```bash
make dashboard-dev        # API on :8501 with auto-reload (needs Redis + config.yaml)
make dashboard-front-dev  # Vite on http://localhost:5173/dashboard/, proxies /dashboard/api to :8501
```

Use `DASHBOARD_API=http://localhost:8511 npm run dev` to point Vite at another API port.
`make dashboard-build` builds `dist/`, after which `dashboard_api.py` serves everything at
http://localhost:8501/dashboard/.

## API conventions

- Mutating requests (`POST/PUT/DELETE`) must send `X-Dashboard-Request: 1`, otherwise 403 (CSRF guard,
  since basic auth credentials are attached to cross-site requests too). `src/api.js` does it.
- Job changes are saved to Redis and marked dirty; the bot picks them up after "Apply"
  (`POST /api/scheduler/reload`).
