import asyncio
import datetime
import functools
import json
import time
from collections import defaultdict
from typing import List
from typing import Optional, Literal

from apscheduler.events import EVENT_JOB_MISSED, EVENT_JOB_ERROR
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from pydantic import BaseModel

from lib.config import Config
from lib.db import DB
from lib.interchan import SimpleRPC
from lib.log_db import RedisLog
from lib.logs import WithLogger
from models.sched import SchedJobCfg


class JobStatsModel(BaseModel):
    last_ts: float | None = None
    run_count: int = 0
    last_elapsed: float | None = None
    total_elapsed: float | None = None
    last_status: Literal["ok", "error", "progress"] | None = None
    last_error: str | None = None
    error_count: int = 0
    next_run_ts: float | None = None
    is_dirty: bool = False
    is_running: bool = False
    creation_ts: float | None = None

    @property
    def avg_elapsed(self) -> float | None:
        if self.run_count and self.total_elapsed:
            return self.total_elapsed / self.run_count
        return None

    model_config = {
        "extra": "ignore"  # ignore unknown Redis fields (safe)
    }


class JobStats(WithLogger):
    def __init__(self, db: DB, key: str):
        super().__init__()
        self.db = db
        self.key = f"{PublicScheduler.DB_KEY_PREFIX}:Stats:{key}"

    async def read_stats(self) -> JobStatsModel:
        data = await self.db.redis.hgetall(self.key)
        return JobStatsModel(**data) if data else JobStatsModel()

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
        await r.hincrby(self.key, 'run_count', 1)
        await r.hincrbyfloat(self.key, 'total_elapsed', float(elapsed))

        if status == "error":
            await r.hincrby(self.key, 'error_count', 1)

        # last-* fields
        mapping = {
            'last_ts': ts,
            'last_elapsed': float(elapsed),
            'last_status': status,
            'last_error': error_message or "",
        }
        await r.hset(self.key, mapping=mapping)

    async def record_progress(self):
        r = self.db.redis
        await r.hset(self.key, 'last_status', "progress")

    async def set_next_time_run(self, ts):
        r = self.db.redis
        await r.hset(self.key, 'next_run_ts', ts)

    async def set_is_dirty(self, is_dirty: bool):
        r = self.db.redis
        await r.hset(self.key, 'is_dirty', str(int(is_dirty)))

    async def set_is_running(self, is_running: bool):
        r = self.db.redis
        await r.hset(self.key, 'is_running', str(int(is_running)))

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
        self._rpc = SimpleRPC(db, channel_prefix=self.DB_KEY_PREFIX)

        self.retries = 3
        self.retry_delay = 5
        self.retry_delay_mult = 2

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

    async def _on_control_message(self, payload):
        # The result of this function is dispatched to the dashboard via pub/sub channel
        await self.db_log.info('control_message', phase='received', message=payload)
        self.logger.warning(f'Received control message: {payload}')
        if not payload or not isinstance(payload, dict):
            self.logger.error(f'Invalid message payload format: {payload}')
            await self.db_log.error('control_message', reason='invalid_format', message=payload)
            return "invalid_format"
        command = payload.get('command')
        if command == self.COMMAND_RELOAD:
            await self.load_config_from_db()
            await self.apply_scheduler_configuration()
            self.logger.info('Scheduler configuration reloaded via control message!')
            await self.db_log.warning('config_reloaded')
            return 'reloaded'
        elif command == self.COMMAND_RUN_NOW:
            job_id = payload.get('job_id')
            if job_id:
                await self.db_log.warning('job_scheduled_now', job_id=job_id)
                return await self.run_job_now_by_id(job_id)
            elif func := payload.get('func'):
                await self.db_log.warning('job_scheduled_now', func=func)
                return await self.run_job_by_function(func)
            else:
                await self.logger.error(f'Cannot run {command} with parameters {payload}')
                return None
        else:
            return "unknown_command"

    async def run_job_now_by_id(self, job_id):
        job_cfg = self.find_job_by_id(job_id)
        if not job_cfg:
            raise RuntimeError(f'Job with id {job_id} not found; cannot run now.')

        coro = self._registered_jobs.get(job_cfg.func)
        if not coro:
            raise RuntimeError(f'Job function {job_cfg.func} is not registered; cannot run job {job_id}.')

        self.logger.info(f'Job {job_id} scheduled to run now via control message!')

        # Run the job immediately
        one_time_cfg = job_cfg.model_copy(update={'enabled': True})
        return await coro(one_time_cfg, with_retries=False)

    async def run_job_by_function(self, func_name: str):
        self.logger.info(f'Function {func_name} is run by name')
        coro = self._registered_jobs.get(func_name)
        return await coro(None, with_retries=False)

    async def post_command(self, command: str, timeout=15.0, **kwargs):
        return await self._rpc({
            'command': command,
            **kwargs
        }, timeout=timeout)

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

    def _with_retry(self, func):
        func_name = func.__name__

        @functools.wraps(func)
        async def wrapper(desc: Optional[SchedJobCfg], with_retries=True):
            current_delay = self.retry_delay
            stats = JobStats(self.db, key=desc.id if desc else f'_direct_{func_name}')
            self.logger.info(f"Starting job with retry logic: {func_name}.")
            await self.db_log.info('run', phase='start', job=func_name)
            start_time = time.monotonic()
            job_id = desc.id if desc else 0
            retry_count = self.retries if with_retries else 1
            for attempt in range(1, retry_count + 1):
                try:
                    if desc and not desc.enabled:
                        # fixme: possible bug, are we sure the "desc" is the latest state?
                        self.logger.warning(f'{func_name}: job disabled during run; skipping execution.')
                        await stats.set_is_running(False)
                        await self.db_log.warning('run', phase='skipped',
                                                  job=func_name, job_id=job_id,
                                                  comment='job disabled during run')
                        return None

                    await stats.set_is_running(True)
                    result = await func()
                    elapsed = time.monotonic() - start_time
                    await self.db_log.info('run', phase='complete',
                                           job=func_name, job_id=job_id, elapsed=elapsed)
                    self.logger.info(
                        f'{func_name}: completed successfully in {elapsed:.2f} seconds on attempt {attempt}.')
                    await stats.record_success(elapsed=elapsed, ts=time.time())
                    await stats.set_is_running(False)
                    result = result if result is not None else 'success'
                    return result
                except Exception as e:
                    error_msg = str(e)
                    self.logger.warning(
                        f"{func_name}: attempt {attempt}/{retry_count} failed: {e}. Retrying in {current_delay} seconds...")

                    elapsed = time.monotonic() - start_time
                    await stats.record_error(elapsed, error_message=error_msg, ts=time.time())
                    await stats.set_is_running(False)

                    if attempt < retry_count:
                        await self.db_log.error('run', phase='retry',
                                                job=func_name, job_id=job_id,
                                                attempt=attempt, error=error_msg)
                        await asyncio.sleep(current_delay)
                        current_delay = current_delay * self.retry_delay
                    else:
                        await self.db_log.error('run', phase='failed',
                                                job=func_name, job_id=job_id,
                                                error=error_msg)
                        self.logger.error(f'{func_name}: all {retry_count} attempts failed.')
                        return f'failed with error: {error_msg}'
            return 'unknown failure'

        return wrapper

    async def start(self):
        if self.scheduler.running:
            self.logger.warning("Scheduler is already running.")
            return
        await self.load_config_from_db()
        self.scheduler.start()
        await self.apply_scheduler_configuration()
        await self._rpc.run_as_server(self._on_control_message)
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

    async def start_rpc_client(self):
        await self._rpc.run_as_client()

    @staticmethod
    def job_distribution(jobs: List[SchedJobCfg]):
        distribution = defaultdict(int)
        for job in jobs:
            distribution[job.func] += 1
        return distribution
