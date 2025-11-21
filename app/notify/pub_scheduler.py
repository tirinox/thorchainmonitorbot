import asyncio
import functools
import json
from typing import List

from apscheduler.events import EVENT_JOB_MISSED, EVENT_JOB_ERROR
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from lib.config import Config
from lib.db import DB
from lib.interchan import PubSubChannel
from lib.log_db import RedisLog
from lib.logs import WithLogger
from models.sched import SchedJobCfg


class PublicScheduler(WithLogger):
    DB_KEY_PREFIX = 'PublicScheduler'
    DB_KEY_CONFIG = f'{DB_KEY_PREFIX}:Config'

    DB_KEY_COMM_CHAN = f'{DB_KEY_PREFIX}:CommunicationChannel'

    def db_key_stats(self, func_name: str) -> str:
        return f'{self.DB_KEY_PREFIX}:Stats:{func_name}'

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
        await self.db_log.add_log_convenience('clear_jobs', 'start', apply=apply, save=save)
        self._scheduled_jobs.clear()
        if apply:
            await self.apply_scheduler_configuration()
        if save:
            await self.save_config_to_db()
        await self.db_log.add_log_convenience('clear_jobs', 'end', apply=apply, save=save)

    @property
    def jobs(self) -> List[SchedJobCfg]:
        return self._scheduled_jobs

    async def _on_control_message(self, _chan, message):
        await self.db_log.add_log_convenience('control_message', 'received', message=message)
        self.logger.warning(f'Received control message: {message}')
        if not message or not isinstance(message, dict):
            self.logger.error(f'Invalid control message format: {message}')
            await self.db_log.add_log_convenience('control_message', 'error', reason='invalid_format', message=message)
            return
        command = message.get('command')
        if command == 'reload_config':
            await self.load_config_from_db()
            await self.apply_scheduler_configuration()
            self.logger.info('Scheduler configuration reloaded via control message!')
            await self.db_log.add_log_convenience('control_message', 'config_reloaded')

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

    async def add_new_job(self, job_cfg: SchedJobCfg, allow_replace=False):
        if not allow_replace:
            if any(existing_job.id == job_cfg.id for existing_job in self._scheduled_jobs):
                self.logger.error(f"Job with id {job_cfg.id} already exists; cannot add duplicate.")
                raise ValueError(f"Job with id {job_cfg.id} already exists.")

        if allow_replace:
            # Remove existing job with the same id
            self._scheduled_jobs = [job for job in self._scheduled_jobs if job.id != job_cfg.id]

        self._scheduled_jobs.append(job_cfg)
        await self.save_config_to_db()
        self.logger.info(f"Added new job {job_cfg.id} of type {job_cfg.func}.")

    def _with_retry(self, func, retries=3, delay=5, delay_mult=2):
        func_name = func.__name__

        @functools.wraps(func)
        async def wrapper():
            current_delay = delay
            self.logger.info(f"Starting job with retry logic: {func_name}.")
            for attempt in range(1, retries + 1):
                try:
                    return await func()
                except Exception as e:
                    self.logger.warning(
                        f"{func_name}: attempt {attempt}/{retries} failed: {e}. Retrying in {current_delay} seconds...")
                    if attempt < retries:
                        await asyncio.sleep(current_delay)
                        current_delay = current_delay * delay_mult
                    else:
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

    async def load_config_from_db(self):
        # Placeholder for loading configuration if needed
        schedule_cfg = await self.db.redis.get(self.DB_KEY_CONFIG)
        schedule_cfg = json.loads(schedule_cfg) if schedule_cfg else []
        if not isinstance(schedule_cfg, list):
            self.logger.error('Invalid schedule configuration format.')
            schedule_cfg = []
        self._scheduled_jobs = [SchedJobCfg(**item) for item in schedule_cfg]
        self.logger.info(f'Loaded scheduler configuration from DB: {len(self._scheduled_jobs)} jobs.')
        return self._scheduled_jobs

    async def save_config_to_db(self):
        self.logger.info(f"Saving scheduler configuration to DB: {len(self._scheduled_jobs)} jobs.")
        schedule_cfg = [job.model_dump() for job in self._scheduled_jobs]
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
            coro = self._registered_jobs.get(job_cfg.func)
            if not coro:
                self.logger.error(f"Job function '{job_cfg.func}' is not registered; skipping job '{job_cfg.id}'.")
                continue

            self.scheduler.add_job(
                coro,
                **job_cfg.to_add_job_args()
            )
