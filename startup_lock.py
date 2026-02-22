from __future__ import annotations

import fcntl
import os
from dataclasses import dataclass


@dataclass
class StartupLock:
    """Single-process lock for polling mode."""

    path: str
    _fd: int | None = None

    def acquire(self) -> bool:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self._fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o644)
        try:
            fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            os.ftruncate(self._fd, 0)
            os.write(self._fd, str(os.getpid()).encode("utf-8"))
            return True
        except BlockingIOError:
            return False

    def release(self) -> None:
        if self._fd is None:
            return
        fcntl.flock(self._fd, fcntl.LOCK_UN)
        os.close(self._fd)
        self._fd = None
