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

## Key data and integration boundaries
- THORChain data comes from thornode + Midgard connectors (`api/aionode`, `api/midgard`), initialized in `create_thor_node_connector`.
- Persistent state is Redis-only (`app/lib/db.py`); Telegram FSM state also uses Redis through `RedisStorage3`.
- Config is YAML + `.env`; `Config` auto-loads `.env` and searches `/config/config.yaml`, `../config.yaml`, then `config.yaml` (`app/lib/config.py`).
- Container topology in `docker-compose.yml`: `thtgbot`, `renderer`, `api`, `dashboard`, `redis`, `nginx`, `dozzle`.
- HTML infographic rendering is an external worker (`infographic_renderer.renderer_url` in `example_config.yaml`, default `http://renderer:8404/render`).

## Productive local workflows
- First-time setup follows `README.md`: copy `example.env` + `example_config.yaml`, then `make start`.
- Main ops commands are in `Makefile`: `make start|stop|restart|logs|attach|test|graph|dashboard-dev|renderer-dev|redis-analysis`.
- Test suite runs from app root: `cd app && python -m pytest tests` (same as `make test`).
- For one-off maintenance against live Redis, follow README caveat commands using `PYTHONPATH="/app"` in container.
- When running scripts locally, prefer `PYTHONPATH=.` from `app/` (pattern used across `Makefile` tools).

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

