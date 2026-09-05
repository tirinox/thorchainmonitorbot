import asyncio
import logging

import pytest

from notify.personal.personal_main import NodeChangePersonalNotifier


@pytest.mark.asyncio
async def test_background_task_failure_is_consumed_and_logged(caplog):
    notifier = NodeChangePersonalNotifier.__new__(NodeChangePersonalNotifier)
    notifier.logger = logging.getLogger('test-node-change-personal-notifier')
    notifier._background_tasks = set()

    async def fail():
        raise RuntimeError('test failure')

    with caplog.at_level(logging.ERROR):
        task = notifier._create_background_task(fail(), name='test-task')
        while task in notifier._background_tasks:
            await asyncio.sleep(0)

    assert task.done()
    assert 'Background task "test-task" failed.' in caplog.text
    assert 'RuntimeError: test failure' in caplog.text
