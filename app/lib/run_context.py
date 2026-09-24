"""
How the current scheduled-job run was started, visible to everything it calls (per asyncio task).

A run started from the dashboard can be a dry "preview" (messages are built but not sent) or a "test" send
(only to broadcasting.test_channels). Neither is a real post, so neither may update any "previous state"
that the next real alert compares against.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Optional


class RunMode:
    NORMAL = 'normal'  # a real run: posts to the configured channels and saves state
    PREVIEW = 'preview'  # builds the messages without sending anything
    TEST = 'test'  # sends only to broadcasting.test_channels

    ALL = (NORMAL, PREVIEW, TEST)


@dataclass(frozen=True)
class RunContext:
    mode: str = RunMode.NORMAL
    run_id: Optional[str] = None

    @property
    def is_real(self) -> bool:
        """Only real runs may persist state (previous values, stats, cooldowns...)."""
        return self.mode == RunMode.NORMAL


_current_run: ContextVar[RunContext] = ContextVar('current_run', default=RunContext())


def current_run() -> RunContext:
    return _current_run.get()


@contextmanager
def run_context(mode: str = RunMode.NORMAL, run_id: Optional[str] = None):
    if mode not in RunMode.ALL:
        raise ValueError(f'Unknown run mode: {mode!r}')
    token = _current_run.set(RunContext(mode, run_id))
    try:
        yield
    finally:
        _current_run.reset(token)
