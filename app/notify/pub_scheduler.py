import asyncio
import datetime
import functools
import json
import time
from typing import List
from typing import Optional, Any, Literal

from apscheduler.events import EVENT_JOB_MISSED, EVENT_JOB_ERROR
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from pydantic import BaseModel

from lib.config import Config
from lib.db import DB
from lib.interchan import PubSubChannel
from lib.log_db import RedisLog
from lib.logs import WithLogger
from models.sched import SchedJobCfg


class JobStatsModel(BaseModel):
    last_ts: float | None = None  # 1. last timestamp run
    run_count: int = 0  # 2. total run times
    last_elapsed: float | None = None  # 3. last elapsed seconds
    avg_elapsed: float | None = None  # 4. avg elapsed seconds
    last_status: Literal["ok", "error", "progress"] | None = None  # 5. last time whether error or not
    last_error: str | None = None  # 6. last error message if it was error
    error_count: int = 0
    next_run_ts: float | None = None
    is_dirty: bool = False
    is_running: bool = False


# ---- Redis-backed stats ----


class JobStats(WithLogger):
    FIELD_LAST_TS = "last_ts"
    FIELD_RUN_COUNT = "run_count"
    FIELD_LAST_ELAPSED = "last_elapsed"
    FIELD_TOTAL_ELAPSED = "total_elapsed"  # internal for avg calc
    FIELD_LAST_STATUS = "last_status"
    FIELD_LAST_ERROR = "last_error"
    FIELD_ERROR_COUNT = "error_count"
    FIELD_NEXT_RUN_TS = "next_run_ts"
    FIELD_IS_DIRTY = "is_dirty"
    FIELD_IS_RUNNING = "is_running"

    def __init__(self, db: DB, key: str):
        super().__init__()
        self.db = db
        self.key = f"{PublicScheduler.DB_KEY_PREFIX}:Stats:{key}"

    # --- simple helpers (not nested) ---

    @staticmethod
    def _to_str(value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, bytes):
            return value.decode("utf-8")
        return str(value)

    @staticmethod
    def _to_int(value: Any, default: int = 0) -> int:
        s = JobStats._to_str(value)
        if s is None or s == "":
            return default
        try:
            return int(s)
        except ValueError:
            return default

    @staticmethod
    def _to_float(value: Any, default: float | None = None) -> float | None:
        s = JobStats._to_str(value)
        if s is None or s == "":
            return default
        try:
            return float(s)
        except ValueError:
            return default

    # --- public API ---

    async def read_stats(self) -> JobStatsModel:
        data = await self.db.redis.hgetall(self.key)
        if not data:
            # default Pydantic instance
            return JobStatsModel()

        last_ts = self._to_float(data.get(self.FIELD_LAST_TS))
        run_count = self._to_int(data.get(self.FIELD_RUN_COUNT), default=0)
        last_elapsed = self._to_float(data.get(self.FIELD_LAST_ELAPSED))
        total_elapsed = self._to_float(data.get(self.FIELD_TOTAL_ELAPSED), default=None)
        last_status = self._to_str(data.get(self.FIELD_LAST_STATUS))
        last_error = self._to_str(data.get(self.FIELD_LAST_ERROR))
        error_count = self._to_int(data.get(self.FIELD_ERROR_COUNT), default=0)
        next_run_ts = self._to_float(data.get(self.FIELD_NEXT_RUN_TS))
        is_dirty = bool(int(self._to_str(data.get(self.FIELD_IS_DIRTY, 0))))
        is_running = bool(int(self._to_str(data.get(self.FIELD_IS_RUNNING, 0))))

        avg_elapsed: float | None = None
        if run_count > 0 and total_elapsed is not None:
            avg_elapsed = total_elapsed / run_count

        return JobStatsModel(
            last_ts=last_ts,
            run_count=run_count,
            last_elapsed=last_elapsed,
            avg_elapsed=avg_elapsed,
            last_status=last_status,  # "ok" / "error" / "progress" / None
            last_error=last_error,
            error_count=error_count,
            next_run_ts=next_run_ts,
            is_dirty=is_dirty,
            is_running=is_running,
        )

    async def _update_common_fields(
            self,
            *,
            elapsed: float,
            ts: Optional[float],
            status: Literal["ok", "error"],
            error_message: Optional[str] = None,
    ) -> None:
        if ts is None:
            ts = time.time()  # or your monotonic source if you prefer

        r = self.db.redis

        # atomic increments
        await r.hincrby(self.key, self.FIELD_RUN_COUNT, 1)
        await r.hincrbyfloat(self.key, self.FIELD_TOTAL_ELAPSED, float(elapsed))

        if status == "error":
            await r.hincrby(self.key, self.FIELD_ERROR_COUNT, 1)

        # last-* fields
        mapping = {
            self.FIELD_LAST_TS: ts,
            self.FIELD_LAST_ELAPSED: float(elapsed),
            self.FIELD_LAST_STATUS: status,
            self.FIELD_LAST_ERROR: error_message or "",
        }
        await r.hset(self.key, mapping=mapping)
        await self.set_is_running(False)

    async def record_progress(self):
        r = self.db.redis
        await r.hset(self.key, self.FIELD_LAST_STATUS, "progress")

    async def set_next_time_run(self, ts):
        r = self.db.redis
        await r.hset(self.key, self.FIELD_NEXT_RUN_TS, ts)

    async def set_is_dirty(self, is_dirty):
        r = self.db.redis
        await r.hset(self.key, self.FIELD_IS_DIRTY, str(int(is_dirty)))

    async def set_is_running(self, is_running: bool):
        r = self.db.redis
        await r.hset(self.key, self.FIELD_IS_RUNNING, str(int(is_running)))

    async def record_success(self, elapsed: float, ts: Optional[float] = None) -> None:
        await self._update_common_fields(
            elapsed=elapsed,
            ts=ts,
            status="ok",
            error_message=None,
        )

    async def record_error(
            self,
            elapsed: float,
            error_message: str,
            ts: Optional[float] = None,
    ) -> None:
        await self._update_common_fields(
            elapsed=elapsed,
            ts=ts,
            status="error",
            error_message=error_message,
        )

    async def reset(self) -> None:
        await self.db.redis.delete(self.key)


class PublicScheduler(WithLogger):
    DB_KEY_PREFIX = 'PublicScheduler'
    DB_KEY_CONFIG = f'{DB_KEY_PREFIX}:Config'

    COMMAND_RELOAD = 'reload_config'
    COMMAND_RUN_NOW = 'run_now'

    ANY_JOB_SPECIAL_ID = '__any_job_check__'

    DB_KEY_COMM_CHAN = f'{DB_KEY_PREFIX}:CommunicationChannel'

    def __init__(self, cfg: Config, db: DB, loop: asyncio.AbstractEventLoop = None):
        super().__init__()

        self.cfg = cfg
        self.db = db

        self.scheduler = AsyncIOScheduler({
            'event_loop': loop or asyncio.get_event_loop(),
        })
        self.scheduler.add_listener(self._fail_listener, EVENT_JOB_MISSED | EVENT_JOB_ERROR)
        self._registered_jobs = {}
        self._scheduled_jobs: List[SchedJobCfg] = []
        self.db_log = RedisLog(self.DB_KEY_PREFIX, db, max_lines=10_000)
        self._subscriber = PubSubChannel(db, self.DB_KEY_COMM_CHAN, self._on_control_message)

    async def clear_job_list(self, apply=False, save=False):
        await self.db_log.info('clear_jobs', phase='start', apply=apply, save=save)
        self._scheduled_jobs.clear()
        if apply:
            await self.apply_scheduler_configuration()
        if save:
            await self.save_config_to_db()
        await self.db_log.info('clear_jobs', phase='end', apply=apply, save=save)

    async def any_job_is_dirty(self):
        any_job = JobStats(self.db, key=self.ANY_JOB_SPECIAL_ID)
        any_job_stats = await any_job.read_stats()
        if any_job_stats.is_dirty:
            return True

        for job in self._scheduled_jobs:
            stats = JobStats(self.db, key=job.id)
            job_stats = await stats.read_stats()
            if job_stats.is_dirty:
                return True
        return False

    @property
    def jobs(self) -> List[SchedJobCfg]:
        return self._scheduled_jobs

    async def _on_control_message(self, _chan, message):
        await self.db_log.info('control_message', phase='received', message=message)
        self.logger.warning(f'Received control message: {message}')
        if not message or not isinstance(message, dict):
            self.logger.error(f'Invalid control message format: {message}')
            await self.db_log.error('control_message', reason='invalid_format', message=message)
            return
        command = message.get('command')
        if command == self.COMMAND_RELOAD:
            await self.load_config_from_db()
            await self.apply_scheduler_configuration()
            self.logger.info('Scheduler configuration reloaded via control message!')
            await self.db_log.warning('config_reloaded')
        elif command == self.COMMAND_RUN_NOW:
            job_id = message.get('job_id')
            await self.db_log.warning('job_scheduled_now', job_id=job_id)
            await self.run_job_now(job_id)

    async def run_job_now(self, job_id):
        job_cfg = self.find_job_by_id(job_id)
        if not job_cfg:
            raise RuntimeError(f'Job with id {job_id} not found; cannot run now.')

        coro = self._registered_jobs.get(job_cfg.func)
        if not coro:
            raise RuntimeError(f'Job function {job_cfg.func} is not registered; cannot run job {job_id}.')

        self.logger.info(f'Job {job_id} scheduled to run now via control message!')
        # Run the job immediately
        await coro(job_cfg)

    async def post_command(self, command: str, **kwargs):
        await self._subscriber.post_message({
            'command': command,
            **kwargs
        })

    async def register_job_type(self, key, func):
        if key in self._registered_jobs:
            self.logger.warning(f"Job {key} is already registered.")
            return

        wrapped_func = self._with_retry(func)
        self._registered_jobs[key] = wrapped_func
        self.logger.info(f"Registered job {key}.")

    async def add_new_job(self, job_cfg: SchedJobCfg, allow_replace=False, load_before=False):
        if not job_cfg.id or job_cfg.id.strip() == "":
            raise ValueError("Job ID cannot be empty.")

        if load_before:
            await self.load_config_from_db()

        exists = any(existing_job.id == job_cfg.id for existing_job in self._scheduled_jobs)
        if exists and not allow_replace:
            self.logger.error(f"Job with id {job_cfg.id} already exists; cannot add duplicate.")
            raise ValueError(f"Job with id {job_cfg.id} already exists.")

        if allow_replace:
            # Remove existing job with the same id
            self._scheduled_jobs = [job for job in self._scheduled_jobs if job.id != job_cfg.id]

        self._scheduled_jobs.append(job_cfg)
        await self.save_config_to_db()
        await self.db_log.info(
            "job_replaced" if exists else "job_created",
            job_id=job_cfg.id,
            job=job_cfg.func,
            variant=job_cfg.variant
        )
        await self._mark_job_dirty(job_cfg.id)
        self.logger.info(f"{'Edited job' if exists else 'Added a new'} job {job_cfg.id} of type {job_cfg.func}.")

    async def _mark_job_dirty(self, job_id: str, value=True):
        stats = JobStats(self.db, key=job_id)
        await stats.set_is_dirty(value)

    def _with_retry(self, func, retries=3, delay=5, delay_mult=2):
        func_name = func.__name__

        @functools.wraps(func)
        async def wrapper(desc: SchedJobCfg):
            # fixme: retries will continue even if the job is cancelled externally
            current_delay = delay
            stats = JobStats(self.db, key=desc.id)
            self.logger.info(f"Starting job with retry logic: {func_name}.")
            await self.db_log.info('run', phase='start', job=func_name)
            start_time = time.monotonic()
            for attempt in range(1, retries + 1):
                try:
                    await stats.set_is_running(True)
                    result = await func()
                    elapsed = time.monotonic() - start_time
                    await self.db_log.info('run', phase='complete', job=func_name, elapsed=elapsed)
                    self.logger.info(
                        f'{func_name}: completed successfully in {elapsed:.2f} seconds on attempt {attempt}.')
                    await stats.record_success(elapsed=elapsed, ts=time.time())
                    return result
                except Exception as e:
                    self.logger.warning(
                        f"{func_name}: attempt {attempt}/{retries} failed: {e}. Retrying in {current_delay} seconds...")

                    elapsed = time.monotonic() - start_time
                    await stats.record_error(elapsed, error_message=str(e), ts=time.time())

                    if attempt < retries:
                        await self.db_log.error('run', phase='retry', job=func_name, attempt=attempt,
                                                error=str(e))
                        await asyncio.sleep(current_delay)
                        current_delay = current_delay * delay_mult
                    else:
                        await self.db_log.error('run', phase='failed', job=func_name, error=str(e))
                        self.logger.error(f'{func_name}: all {retries} attempts failed.')
                        raise
            return None

        return wrapper

    async def start(self):
        if self.scheduler.running:
            self.logger.warning("Scheduler is already running.")
            return
        await self.load_config_from_db()
        self.scheduler.start()
        self._subscriber.start()
        self.logger.info("Scheduler started.")

    def stop(self):
        if not self.scheduler.running:
            self.logger.warning("Scheduler is not running.")
            return
        self.scheduler.shutdown()
        self.logger.info("Scheduler stopped.")

    async def load_config_from_db(self, silent=False) -> List[SchedJobCfg]:
        # Placeholder for loading configuration if needed
        schedule_cfg = await self.db.redis.get(self.DB_KEY_CONFIG)
        schedule_cfg = json.loads(schedule_cfg) if schedule_cfg else []
        if not isinstance(schedule_cfg, list):
            self.logger.error('Invalid schedule configuration format.')
            schedule_cfg = []
        self._scheduled_jobs = [SchedJobCfg(**item) for item in schedule_cfg]
        if not silent:
            self.logger.info(f'Loaded scheduler configuration from DB: {len(self._scheduled_jobs)} jobs.')
        return self._scheduled_jobs

    async def save_config_to_db(self):
        self.logger.info(f"Saving scheduler configuration to DB: {len(self._scheduled_jobs)} jobs.")
        schedule_cfg = [job.model_dump(mode='json') for job in self._scheduled_jobs]
        await self.db.redis.set(self.DB_KEY_CONFIG, json.dumps(schedule_cfg))

    def _fail_listener(self, event):
        if event.exception:
            self.logger.error(f"Job {event.job_id} failed with exception: {event.exception}")
        else:
            self.logger.info(f"Job {event.job_id} completed successfully.")

    async def apply_scheduler_configuration(self):
        """
        Apply the current scheduler configuration.
        All self.jobs are re-added to the scheduler.
        """
        for existing_job in self.scheduler.get_jobs():
            self.scheduler.remove_job(existing_job.id)

        for job_cfg in self._scheduled_jobs:
            await self._mark_job_dirty(job_cfg.id, value=False)

            if not job_cfg.enabled:
                continue

            coro = self._registered_jobs.get(job_cfg.func)
            if not coro:
                self.logger.error(f"Job function '{job_cfg.func}' is not registered; skipping job '{job_cfg.id}'.")
                continue

            j = self.scheduler.add_job(
                coro,
                **job_cfg.to_add_job_args(),
                args=[job_cfg],
            )

            if isinstance(j.next_run_time, datetime.datetime):
                stats = JobStats(self.db, job_cfg.id)
                await stats.set_next_time_run(j.next_run_time.timestamp())

        await self._mark_job_dirty(self.ANY_JOB_SPECIAL_ID, value=False)

        self.logger.info(
            f'Applied scheduler configuration: {self.total_running_jobs} / {len(self._scheduled_jobs)} jobs scheduled.')

    def find_job_by_id(self, job_id: str) -> SchedJobCfg | None:
        for job in self._scheduled_jobs:
            if job.id == job_id:
                return job
        return None

    def find_jobs_by_func(self, func_name: str) -> List[SchedJobCfg]:
        return [job for job in self._scheduled_jobs if job.func == func_name]

    async def toggle_job_enabled(self, job_id: str, enabled: bool):
        job = self.find_job_by_id(job_id)
        if not job:
            self.logger.error(f"Job with id '{job_id}' not found; cannot toggle enabled state.")
            raise ValueError(f"Job with id '{job_id}' not found.")

        if enabled != job.enabled:
            job.enabled = enabled
            await self._mark_job_dirty(job_id)
            await self.save_config_to_db()
            self.logger.info(f"Toggled job '{job_id}' enabled state to {enabled}.")
            await self.db_log.info('job_toggle_enabled', job_id=job_id, enabled=enabled)
        else:
            self.logger.info(f"Job '{job_id}' already has enabled state {enabled}; no change made.")

    @property
    def total_running_jobs(self) -> int:
        return len(self.scheduler.get_jobs())

    async def delete_job(self, job_id: str):
        job = self.find_job_by_id(job_id)
        if not job:
            self.logger.error(f"Job with id '{job_id}' not found; cannot delete.")
            raise ValueError(f"Job with id '{job_id}' not found.")
        self._scheduled_jobs = [j for j in self._scheduled_jobs if j.id != job_id]

        await self._mark_job_dirty(self.ANY_JOB_SPECIAL_ID, value=True)

        stats = JobStats(self.db, key=job_id)
        await stats.reset()
        await self.save_config_to_db()
        await self.db_log.info('job_deleted', job_id=job_id, job=job.func)
        self.logger.info(f"Deleted job '{job_id}'.")

    async def get_job_stats(self, job_id: str) -> JobStatsModel:
        stats_db = JobStats(self.db, key=job_id)
        return await stats_db.read_stats()
