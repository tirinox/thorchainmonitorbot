# AGENTS.md

## Project purpose and runtime model
- This repo runs a THORChain monitoring bot that fans out alerts to Telegram, Discord, Slack, and Twitter; core startup is `app/main.py` (`App.run_bot`).
- The app is event-driven: fetchers/decoders publish events to notifiers, which publish formatted messages via `notify/alert_presenter.py` and `notify/broadcast.py`.
- Shared runtime state is centralized in `app/lib/depcont.py` (`DepContainer`), used as the dependency hub for connectors, caches, bots, schedulers, and holders.

## Core architecture to understand before editing
- Startup order matters: `on_startup -> _run_background_jobs -> create_thor_node_connector -> _prepare_task_graph -> _preloading` in `app/main.py`.
- Preload gates bot readiness (`_preloading`): Redis ping, last block fetch, pool cache fetch, node/mimir preload, then public scheduler starts.
- Public scheduled alerts are configured in one place: `app/notify/pub_configure.py` (`PublicAlertJobExecutor.AVAILABLE_TYPES`).
- Two scheduling domains exist: personal scheduler (`PrivateScheduler` in `app/main.py`) and public scheduler (`PublicScheduler` via `configure_jobs`).
- API server is separate from bot process: `app/web_api.py` (Starlette + Uvicorn) reuses Redis/config and exposes settings/stats/name/slack endpoints.
- Admin dashboard is another separate process: `app/dashboard_api.py` (FastAPI, package `app/dashboard/`) serves a JSON API under `/api` plus the Vue 3 + PrimeVue 4 SPA from `web/dashboard/` (built to `dist/`). It talks to the bot only via Redis (scheduler config/stats, `Flagship` flags, RPC `PublicScheduler.post_command`). nginx exposes it at `/dashboard/` behind basic auth; mutating requests must send the `X-Dashboard-Request: 1` header (CSRF guard). Live updates: the bot publishes events via `lib/events.py` (`publish_event`, never raises) to Redis channel `Dashboard:Events`; the dashboard streams them over SSE (`/api/events`), and "run now" is async (202 + `run` events). Dashboard mutations are audited (`dashboard/audit.py`, user from nginx `X-Remote-User`); the home page health checks live in `dashboard/services/summary.py`. Scheduled jobs run in a mode from `lib/run_context.py` (normal / preview / test): new job code that saves "previous state" must go through `PublicAlertJobExecutor._save_state`, and must send only via `_send_alert` (the Broadcaster), so previews and test sends stay side-effect free. The Achievements page (`dashboard/services/achievements.py`) reads the tracker's records (`Achievements:*`) and last fed values (hash `AchievementsLive`), and previews a post through `Broadcaster.capture` without touching the records.

## Key data and integration boundaries
- THORChain data comes from thornode + Midgard connectors (`api/aionode`, `api/midgard`), initialized in `create_thor_node_connector`.
- Persistent state is Redis-only (`app/lib/db.py`); Telegram FSM state also uses Redis through `RedisStorage3`.
- Config is YAML + `.env`; `Config` auto-loads `.env` and searches `/config/config.yaml`, `../config.yaml`, then `config.yaml` (`app/lib/config.py`).
- Container topology in `docker-compose.yml`: `thtgbot`, `renderer`, `api`, `dashboard`, `redis`, `keydb`, `nginx`, `certbot` (renews nginx's Let's Encrypt certificate), `dozzle`.
- HTML infographic rendering is an external worker (`infographic_renderer.renderer_url` in `example_config.yaml`, default `http://renderer:8404/render`).

## Productive local workflows
- First-time setup follows `README.md`: copy `example.env` + `example_config.yaml`, then `make start`.
- Main ops commands are in `Makefile`: `make start|stop|restart|logs|attach|test|graph|dashboard-dev|dashboard-front-dev|dashboard-build|renderer-dev|renderer-demos|redis-analysis`.
- Test suite runs from app root: `cd app && python -m pytest tests` (same as `make test`).
- Regression corpus of real THORChain txs: `app/tests/regression/tx_corpus/*.json.gz`, replayed offline through the block scanner swap detectors and notifiers by `tests/test_tx_corpus.py` (harness in `tests/regression/harness.py`, frozen production thresholds in `tx_corpus/thresholds.yaml`). Find, record, re-record, report and approve cases with `PYTHONPATH=. python tools/tx_corpus.py find|add|rerecord|report|approve`. A bot bug found by a case goes to its `known_issues` until fixed; the test then says to remove it.
- For one-off maintenance against live Redis, follow README caveat commands using `PYTHONPATH="/app"` in container.
- When running scripts locally, prefer `PYTHONPATH=.` from `app/` (pattern used across `Makefile` tools).
- Achievement card frames (the wreath backgrounds of `renderer/templates/achievement.jinja2`): before adding or repainting one, read `docs/achievement-frames.md` — design rules, prompt template, `tools/achievement_frame.py` (generate via OpenRouter, measure the hole and edge color, preview a real card) and the `WreathStyle` table. The per-frame styles live in `data/renderer/achievement_frames.json` (not in Python); the renderer's frame tuner (`/render/frames`, `renderer/frames.py`) sets the hole by eye and writes that file and the achievement demos.
- Node infographic (`renderer/templates/nodes.jinja2`, posted after a node churn and from the Telegram menu): its parameters are built by `comm/picture/nodes_card.py`. The owner of a node's IP address is named by `data/cloud_providers.yaml` (`models/cloud_provider.py`): by the AS number first, then by a whole word of the GeoIP names; add a provider there, not in Python. The template clusters the nodes on its maps itself; the land of the dotted maps is `data/renderer/static/js/world_land.js`, made by `tools/world_land_mask.py` from `data/earth-bg.png`. Demos for the gallery: `tools/debug/dbg_geo_ip.py` with `SAVE_GALLERY_DEMOS`.

- Pool activated card (`renderer/templates/pool_activated.jinja2`, parameters from `comm/picture/pool_card.py`): `PoolChurnNotifier` hands `PoolChanges` with the pool snapshot and the RUNE price, and `AlertPresenter._handle_pool_churn` posts one card per activated pool (`PoolChanges.activated`), one after another, with the usual text of that pool as the caption; every other change goes in one plain text, as before, and without `use_html_renderer` everything stays one text. The confetti and fireworks are drawn by the template script, seeded by the pool name. Logos: a new or activated pool is checked by `PoolChurnNotifier.check_logos` (`check_pool_logos` in `comm/picture/crypto_logo.py`: the logo of the asset and the badge of its chain, downloaded from trustwallet if missing) and a logo that cannot be got goes to the emergency report; `tools/ensure_downloaded_asset_logo.py` does the same for all current pools. Demos: `tools/debug/dbg_pool_churn.py` with `SAVE_GALLERY_DEMOS`.

## Codebase-specific patterns and conventions
- Many components implement subscriber chaining (`add_subscriber`); extend pipelines by inserting a stage, not by bypassing existing notifiers.
- Feature toggles are config-driven booleans (examples: `tx.*.enabled`, `native_scanner.enabled`, `price.divergence.*`) and checked in `_prepare_task_graph`.
- Error handling often degrades by retry/backoff at startup (`_preloading`) and emergency reporting (`lib/emergency.py`) rather than crashing immediately.
- Keep cross-channel messaging abstracted via `DepContainer.get_messenger` and broadcaster/presenter layers; avoid direct platform calls from fetchers.
- Existing tests are mostly unit-style and include async tests (`pytest.mark.asyncio`) under `app/tests/`.

## Agent guardrails for edits
- Preserve startup sequencing and preload guarantees; moving scheduler start earlier can produce empty/invalid alerts.
- Add new recurring public alerts by wiring `PublicAlertJobExecutor` + `AVAILABLE_TYPES`, not ad-hoc loops.
- For new config keys, mirror existing access style (`cfg.get`, `as_*`, defaults) and document examples in `example_config.yaml`.
- Prefer minimal invasive changes in `app/main.py`; it is a high-coupling orchestration file touching most subsystems.
- There were no existing AI policy files found via glob search beyond `README.md`; this file is the primary agent guidance baseline.

