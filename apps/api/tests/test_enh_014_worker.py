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


def test_worker_and_beat_log_through_the_app_json_formatter():
    """O-1 (spec §6.5): Celery's setup_logging hook installs the app's JsonFormatter, so `extra_fields` (delivery id,
    channel, status, attempt) reach the worker/beat logs instead of being dropped by Celery's default format."""
    from celery.signals import setup_logging

    from app import worker
    from app.core.logging import JsonFormatter

    root = logging.getLogger()
    saved_handlers, saved_level = root.handlers[:], root.level
    try:
        assert any(receiver() is worker.configure_worker_logging for _, receiver in setup_logging.receivers)
        worker.configure_worker_logging()
        assert isinstance(root.handlers[0].formatter, JsonFormatter)
    finally:
        root.handlers[:] = saved_handlers
        root.setLevel(saved_level)
