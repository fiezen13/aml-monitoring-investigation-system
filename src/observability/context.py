from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

_CONTEXT: ContextVar[dict[str, Any]] = ContextVar("fin07_log_context", default={})


def current_context() -> dict[str, Any]:
    return dict(_CONTEXT.get())


@contextmanager
def bind_context(**fields: Any) -> Iterator[None]:
    clean = {key: value for key, value in fields.items() if value is not None}
    token = _CONTEXT.set({**_CONTEXT.get(), **clean})
    try:
        yield
    finally:
        _CONTEXT.reset(token)
