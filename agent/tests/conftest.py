"""Shared test configuration."""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Callable, Mapping
from typing import Any


def pytest_asyncio_loop_factories(
    config: Any, item: Any
) -> Mapping[str, Callable[[], asyncio.AbstractEventLoop]] | None:
    # psycopg's async mode cannot run on Windows' default ProactorEventLoop.
    if sys.platform == "win32":
        return {"selector": asyncio.SelectorEventLoop}
    return None
