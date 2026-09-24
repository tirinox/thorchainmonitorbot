import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, Optional

from lib.db import DB
from lib.events import publish_event, EventType
from notify.pub_scheduler import PublicScheduler


class RunStatus:
    RUNNING = 'running'
    SUCCESS = 'success'
    FAILED = 'failed'
    TIMEOUT = 'timeout'  # no answer from the bot in time; the job may still be running there
    ERROR = 'error'  # the RPC itself failed

    FINISHED = (SUCCESS, FAILED, TIMEOUT, ERROR)


class RunConflict(Exception):
    pass


@dataclass
class RunInfo:
    run_id: str
    job_id: Optional[str]
    func: Optional[str]
    actor: Optional[str] = None
    args: dict[str, Any] = field(default_factory=dict)
    timeout: float = 0.0
    status: str = RunStatus.RUNNING
    result: Any = None
    started_ts: float = field(default_factory=time.time)
    finished_ts: Optional[float] = None

    @property
    def is_active(self):
        return self.status == RunStatus.RUNNING

    def to_dict(self):
        return asdict(self)


class RunManager:
    """
    "Run now" without holding an HTTP request open: the RPC to the bot is awaited in a background task
    and every state change is published as a `run` event (the dashboard's SSE stream delivers it).
    """

    KEEP_FINISHED = 50

    def __init__(self, scheduler: PublicScheduler, db: DB):
        self.scheduler = scheduler
        self.db = db
        self._runs: dict[str, RunInfo] = {}
        self._tasks: set[asyncio.Task] = set()

    def list(self) -> list[dict]:
        return [r.to_dict() for r in sorted(self._runs.values(), key=lambda r: -r.started_ts)]

    def get(self, run_id: str) -> Optional[RunInfo]:
        return self._runs.get(run_id)

    def start(self, *, job_id: Optional[str] = None, func: Optional[str] = None,
              args: Optional[dict] = None, timeout: float = 3600.0, actor: Optional[str] = None) -> RunInfo:
        if job_id and any(r.is_active and r.job_id == job_id for r in self._runs.values()):
            raise RunConflict(f'Job {job_id!r} is already running')

        run = RunInfo(run_id=uuid.uuid4().hex[:12], job_id=job_id, func=func, args=dict(args or {}),
                      timeout=timeout, actor=actor)
        self._runs[run.run_id] = run
        self._prune()

        task = asyncio.create_task(self._execute(run))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return run

    async def _publish(self, run: RunInfo):
        await publish_event(self.db, EventType.RUN, run=run.to_dict())

    async def _execute(self, run: RunInfo):
        await self._publish(run)
        sched = self.scheduler
        target = {'job_id': run.job_id} if run.job_id else {'func': run.func, 'args': run.args}
        try:
            result = await sched.post_command(sched.COMMAND_RUN_NOW, timeout=run.timeout,
                                              run_id=run.run_id, **target)
            run.result = result
            run.status = RunStatus.SUCCESS if result == 'success' else RunStatus.FAILED
        except asyncio.TimeoutError:
            run.status = RunStatus.TIMEOUT
            run.result = f'No answer from the bot in {run.timeout:.0f} s; the job may still be running.'
        except asyncio.CancelledError:
            # the dashboard is shutting down; the job itself keeps running in the bot
            run.status = RunStatus.ERROR
            run.result = 'Dashboard stopped while waiting for the result'
            run.finished_ts = time.time()
            raise
        except Exception as e:
            logging.exception(f'Run {run.run_id} failed')
            run.status = RunStatus.ERROR
            run.result = str(e)

        run.finished_ts = time.time()
        await self._publish(run)

    def _prune(self):
        finished = sorted((r for r in self._runs.values() if not r.is_active), key=lambda r: r.started_ts)
        for r in finished[:max(0, len(finished) - self.KEEP_FINISHED)]:
            del self._runs[r.run_id]

    async def close(self):
        for task in list(self._tasks):
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
