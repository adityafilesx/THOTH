import os
import signal
import threading
import time
from collections.abc import Callable, Mapping

import uvicorn

from thoth_daemon.app import create_app
from thoth_daemon.config import Settings


def _managed_parent_pid(environment: Mapping[str, str]) -> int | None:
    raw = environment.get("THOTH_DESKTOP_PARENT_PID")
    if raw is None:
        return None
    try:
        parent_pid = int(raw)
    except ValueError:
        return None
    return parent_pid if parent_pid > 1 else None


def _process_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _monitor_parent(
    parent_pid: int,
    *,
    process_exists: Callable[[int], bool] = _process_exists,
    terminate: Callable[[], None] | None = None,
    poll_seconds: float = 0.25,
) -> None:
    while process_exists(parent_pid):
        time.sleep(poll_seconds)
    if terminate is None:
        os.kill(os.getpid(), signal.SIGTERM)
    else:
        terminate()


def run() -> None:
    settings = Settings()
    parent_pid = _managed_parent_pid(os.environ)
    if parent_pid is not None:
        threading.Thread(
            target=_monitor_parent,
            args=(parent_pid,),
            name="thoth-parent-monitor",
            daemon=True,
        ).start()
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port, log_level="info")


if __name__ == "__main__":
    run()
