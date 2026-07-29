"""Điều phối tác vụ của worker — không cần Redis hay PostgreSQL."""

import json
from unittest.mock import MagicMock, patch

from src.worker import main as worker


def test_known_job_type_reaches_its_handler():
    with patch.dict(worker.HANDLERS, {"ping": MagicMock()}, clear=False) as handlers:
        worker.process(json.dumps({"job_id": "job-1", "type": "ping", "payload": {"x": 1}}))
        handlers["ping"].assert_called_once_with({"x": 1})


def test_unknown_job_type_is_logged_not_raised(caplog):
    """Tác vụ lạ không được làm chết worker: một tác vụ hỏng thì cả hàng đợi
    đứng, và đó là sự cố nặng hơn nhiều so với một dòng log."""
    worker.process(json.dumps({"job_id": "job-2", "type": "khong_ton_tai", "payload": {}}))
    assert "khong_ton_tai" in caplog.text


def test_handler_failure_does_not_kill_the_loop(caplog):
    boom = MagicMock(side_effect=RuntimeError("bảng biến mất"))
    with patch.dict(worker.HANDLERS, {"ping": boom}, clear=False):
        worker.process(json.dumps({"job_id": "job-3", "type": "ping", "payload": {}}))
    assert "job-3" in caplog.text


def test_every_handler_is_callable():
    assert worker.HANDLERS
    assert all(callable(handler) for handler in worker.HANDLERS.values())
