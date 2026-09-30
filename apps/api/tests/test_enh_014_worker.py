"""ENH-014 Task 6 fix: the worker task must close its DB pool on the loop that opened it."""

import gc
import logging
import warnings
from uuid import uuid4

from app.worker import deliver_notification_task, sweep_stale_deliveries_task


def test_repeated_worker_runs_leave_no_pool_errors_or_unclosed_sockets(caplog):
    gc.collect()  # flush sockets earlier tests left unclosed, so their ResourceWarning is not blamed on this run
    with caplog.at_level(logging.ERROR), warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        results = [deliver_notification_task(str(uuid4())) for _ in range(3)]
    assert results == [None, None, None]
    assert not [r for r in caplog.records if r.name.startswith("sqlalchemy.pool")]
    assert not [w for w in caught if issubclass(w.category, ResourceWarning) and "unclosed" in str(w.message)]


def test_repeated_sweeper_runs_leave_no_pool_errors_or_unclosed_sockets(caplog):
    gc.collect()  # flush sockets earlier tests left unclosed, so their ResourceWarning is not blamed on this run
    with caplog.at_level(logging.ERROR), warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        results = [sweep_stale_deliveries_task() for _ in range(3)]
    assert all(isinstance(r, dict) and {"requeued", "interrupted"} <= r.keys() for r in results)
    assert not [r for r in caplog.records if r.name.startswith("sqlalchemy.pool")]
    assert not [w for w in caught if issubclass(w.category, ResourceWarning) and "unclosed" in str(w.message)]
